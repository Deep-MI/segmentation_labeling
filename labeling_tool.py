import argparse
import shutil
import sys
import os
import random
import subprocess
import signal
import time
import readline

import pandas as pd
import uuid
from tqdm import tqdm
import nibabel as nib
import numpy as np


HELPTEXT = """

Script to label which of two segmentation methods gives better output on a list of images.

USAGE:

labeling.py --method1 <method|random> --method2 <method|random>

Description:
Randomly iterates through a list of subjects. The program then displays a 
view includng segmentations of either the two given methods or randomly (specified in --method1 
and --method2). 'subject_name,method1,method2,result,user,time'. To ensure an unbiased vote, the method number
are shuffled (segmentation1 can be created by method1 or method2 in each step)
The view is chosen to highlight large segmentation differences.

Original Author: Andreas Girodi
Date: Jul-14-2023
Adapted for segmentation by: Clemens Pollak
Date: Sept-5-2023
"""


def options_parse():
    """
    Command line option parser
    """
    parser = argparse.ArgumentParser(usage=HELPTEXT)
    parser.add_argument('-m1', '--method1', dest='met1',
                      help="Name of the first method to use.", required=True)
    parser.add_argument('-m2', '--method2', dest='met2',
                      help="Name of the second method to use.", required=True)
    parser.add_argument('-o','--output_file', dest='result',
                      help='csv file where results should be saved', required=True)
    parser.add_argument('--user ', dest='user', help="Name of the labeler", default=os.environ.get('USER'))
    parser.add_argument('-i', '--input_data', dest='input_file',
                      help='Csv file with the input data. The file should contain the following columns: "subjectID", "image", "method1", "method2"',
                      default=None, required=True)
    parser.add_argument('--diff_maps_dir', dest='diff_maps',
                      help='Directory where difference maps are stored', required=True)
    parser.add_argument('--fs', dest='fs',
                      help='Path to the Freesurfer home',
                      default=None)
    
    args = parser.parse_args()

    # assert(args.met1 in METHODS), f'[ERROR] {args.met1} is not a valid method. Valid methods are: {", ".join(METHODS)}'
    # assert(args.met2 in METHODS), f'[ERROR] {args.met2} is not a valid method. Valid methods are: {", ".join(METHODS)}'

    return args


def stop_labeling(processes: list):
    """
    Stop labeling process,
    write leftover cases into the rest list - TODO: this should be done periodically to account for crashes

    process: list of processes to terminate
    subject_list: cases still left 
    rest: filename of list to write the rest of the data to
    """
    print('[INFO] Stopping labeling')

    for p in processes:
        if sys.platform == "darwin":
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        else:
            p.send_signal(signal.SIGTERM)

    time.sleep(1)

    sys.exit(0)


def run_freeview(diff_map_dir, subject_id, image, seg1, seg2, center, freesurfer_path, xdotool_installed):
    """
    Run freeview command
    """
    # create UID for the process
    uid = uuid.uuid4()

    # print(subject_id)
    # print(image)
    # print(seg1)
    # print(seg2)

    # adapt paths for MacOS
    if sys.platform == "darwin":
        image = image.replace('/groups/','/Volumes/')
        seg1 = seg1.replace('/groups/','/Volumes/')
        seg2 = seg2.replace('/groups/','/Volumes/')



    # create mask around the area of interest
    orig_image = nib.load(image)
    mask = np.ones(orig_image.shape)
    mask[int(center[0])-20:int(center[0])+20, int(center[1])-20:int(center[1])+20, int(center[2])-20:int(center[2])+20] = 0

    if not os.path.isdir('/tmp/labeling'):
        os.mkdir('/tmp/labeling/')

    # save mask
    mask_img = nib.Nifti1Image(mask, orig_image.affine, orig_image.header)
    mask_file = os.path.join('/tmp', 'labeling', f'mask_{uid}.nii.gz')
    nib.save(mask_img, mask_file)

    # copy aseg files to /tmp

    plt_path_seg1 = f'/tmp/labeling/{uid}_{subject_id}_seg1.mgz'
    plt_path_seg2 = f'/tmp/labeling/{uid}_{subject_id}_seg2.mgz'
    shutil.copy(seg1, plt_path_seg1)
    shutil.copy(seg2, plt_path_seg2)




    cmd = [f'{freesurfer_path}/bin/freeview',
            f'{image}:lock=1',
            f'{diff_map_dir}/{subject_id}.nii.gz:colormap=jet:colorscale=0,1:visible=0:opacity=0.25:lock=1:name=difference_map' if args.diff_maps is not None else '',
            f'{plt_path_seg1}:colormap=lut:name=1:visible=0:opacity=0.25',
            f'{plt_path_seg2}:colormap=lut:name=2:visible=1:opacity=0.25',
            f'{mask_file}:colormap=gecolor:colorscale=0,1:visible=1:opacity=0.3:lock=1:name=mask',
            f'-slice {round(center[0])} {round(center[1])} {round(center[2])}',
            f'-subtitle "{subject_id} - UID: {uid}"',
            '-cc',
            '-zoom 4']
        
    

    p = subprocess.Popen(' '.join(cmd), shell=True, stdout=subprocess.DEVNULL, preexec_fn=os.setpgrp if sys.platform == "darwin" else None)

    # sleep one second
    time.sleep(1)

    if xdotool_installed:
        window_hide_command = f'xdotool windowunmap --sync $(xdotool search --name "UID: {uid}")'
        #print(window_hide_command)
        subprocess.run(window_hide_command, shell=True)#, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    return p, uid


def question_loop(p, methods):
    """
    Loop to ask questions
    """
    print(f'[INFO] Awaiting answers. Type in "stop" at any point to stop labeling')

    best = ''
    confidence = ''
    fail = ''

    # first question loop
    valid = False
    try:
        while not valid:
            answer = input(
                '[QUESTION] Which segmentation is better?'
                ' If there is no discernible difference in quality choose a random number.\n'
                'Possible answers:\n'
                '- "1" if segmentation #1 is better\n'
                '- "2" if segmentation #2 is better\n')

            if answer == 'stop':
                stop_labeling(p)
            elif answer in ['1', '2']:
                valid = True

                if answer == '1':
                    best = methods[0]
                elif answer == '2':
                    best = methods[1]
                else:
                    raise ValueError(f'[ERROR] "{answer}" is an invalid input.')
            else:
                print(f'[ERROR] "{answer}" is an invalid input.')
    except KeyboardInterrupt:
        stop_labeling(p)

    # second question loop
    valid = False
    try:
        while not valid:
            answer = input(
                '[QUESTION] Choose your confidence in the rating.\n'
                'Possible answers:\n'
                '- "1" chosen randomly\n'
                '- "2" uncertain\n'
                '- "3" certain\n')

            if answer == 'stop':
                stop_labeling(p)
            elif answer in ['1', '2', '3']:
                valid = True

                if answer == '1':
                    confidence = 'random'
                elif answer == '2':
                    confidence = 'uncertain'
                elif answer == '3':
                    confidence = 'certain'
                else:
                    raise ValueError(f'[ERROR] "{answer}" is an invalid input.')
            else:
                print(f'[ERROR] "{answer}" is an invalid input.')
    except KeyboardInterrupt:
        stop_labeling(p)

    
    # third question loop
    valid = False
    try:
        while not valid:
            answer = input(
                '[QUESTION] How big is the difference between the two segmentations?\n'
                'Possible answers:\n'
                '- "0" no discernible difference\n'
                '- "1" marginal difference\n'
                '- "2" moderate difference\n'
                '- "3" substantial difference\n')
            
            if answer == 'stop':
                stop_labeling(p)
            elif answer in ['0','1', '2', '3']:
                valid = True

                difference_strength = int(answer)
            else:
                print(f'[ERROR] "{answer}" is an invalid input.')
    except KeyboardInterrupt:
        stop_labeling(p)


    # fourth question loop
    valid = False
    try:
        while not valid:
            answer = input(
                '[QUESTION] Did one of the segmentations fail?\n'
                'Possible answers:\n'
                '- "0" no failures\n'
                '- "1" segmentation 1 failed\n'
                '- "2" segmentation 2 failed\n'
                '- "3" both failed\n')

            if answer == 'stop':
                stop_labeling(p)
            elif answer in ['0', '1', '2', '3']:
                valid = True

                if answer == '0':
                    fail = 'None'
                elif answer == '1':
                    fail = methods[0]
                elif answer == '2':
                    fail = methods[1]
                elif answer == '3':
                    fail = f'{methods[0]}+{methods[1]}'
                else:
                    raise ValueError(f'[ERROR] "{answer}" is an invalid input.')
            else:
                print(f'[ERROR] "{answer}" is an invalid input.')
    except KeyboardInterrupt:
        stop_labeling(p)

    # fifth question loop
    valid = False
    try:
        while not valid:
            answer = input(
                '[COMMENT] Please leave comments on the viewed segmentations.\n'
                'Press enter to skip.\n')
            
            if answer == 'stop':
                stop_labeling(p)
            else:
                valid = True
                comment = answer
    except KeyboardInterrupt:
        stop_labeling(p)

    return best, confidence, difference_strength, fail, comment


if __name__ == '__main__':
    args = options_parse()

    # check if xdotool is installed
    xdotool_installed = False
    try:
        subprocess.run(['xdotool', '--version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        xdotool_installed = True
    except FileNotFoundError:
        print('[WARNING] xdotool not installed. Please install xdotool to enable automatic window management.')

    if args.fs is None:
        if os.environ["FREESURFER_HOME"] is not None:
            freesurfer_path = os.environ["FREESURFER_HOME"]
        else:
            paths_to_try = ['/groups/ag-reuter/software/centos/freesurfer741',
                            '/Applications/freesurfer/7.1.1']
            for p in paths_to_try:
                if os.path.isdir(paths_to_try):
                    freesurfer_path = p
                    break

    if args.user is None:
        print('[ERROR] User name could not be determined. Please specify a user name with --user')
        sys.exit(1)

    print(f'[INFO] Labeling {args.met1} and {args.met2} as user {args.user}')

    diff_areas = pd.read_csv(args.input_file, index_col='subject_id') # TODO: put dir
    #diff_areas = diff_areas.sort_values(by='peak_value', ascending=False)

    # read subject names
    num_subjects = len(diff_areas['ID'])
    print(f'[INFO] Loaded list of {num_subjects} cases')

    
    p_next = None
    uid_next = None

    already_labeled = 0

    print(f'[INFO] saving results in {os.path.abspath(args.result)}')

    if os.path.isfile(args.result):
        with open(args.result, mode='r') as results_file:
            already_labeled_subjs = pd.read_csv(results_file, header=None).iloc[:,0].tolist()

        # remove already labeled subjects
        before_del_len = len(diff_areas)
        diff_areas = diff_areas[~diff_areas['ID'].isin(already_labeled_subjs)]
        after_del_len = len(diff_areas)
        print(f'[INFO] Removed {before_del_len - after_del_len} already labeled subjects')

        


    for (subject_id, row), (subject_id_next, row_next) in zip(diff_areas[:-1].iterrows(), diff_areas[1:].iterrows()):

        num_differences = row['num_differences']        

    
        if p_next is None:
            # intialize variables
            method_idx = [0, 1]
            method_names = [args.met1, args.met2]

            # set first window
            image = row['image']
            center = row['x1'], row['y1'], row['z1']            
            random.shuffle(method_idx)            
            methods = [method_names[i] for i in method_idx]
            segmentations = row[args.met1], row[args.met2]
            segmentations = [segmentations[i] for i in method_idx]
            p, uid = run_freeview(args.diff_maps, subject_id, image, segmentations[0], segmentations[1], center, freesurfer_path, xdotool_installed)

            # set next window
            image_next = row_next['image']
            center_next = row_next['x1'], row_next['y1'], row_next['z1']
            random.shuffle(method_idx)
            methods_next = [method_names[i] for i in method_idx]
            segmentations_next = row_next[args.met1], row_next[args.met2]
            segmentations_next = [segmentations_next[i] for i in method_idx]
            p_next, uid_next = run_freeview(args.diff_maps, subject_id_next, image_next, segmentations_next[0], segmentations_next[1], center_next, freesurfer_path, xdotool_installed)
            print('initializing window ...')
            for _ in tqdm(range(10)):
                time.sleep(1.2)
        else:
            p = p_next
            uid = uid_next
            image, methods, segmentations = image_next, methods_next, segmentations_next
            center = center_next

            # set next window
            image_next = row_next['image']
            center_next = row_next['x1'], row_next['y1'], row_next['z1']
            random.shuffle(method_idx)
            methods_next = [method_names[i] for i in method_idx]
            segmentations_next = row_next[args.met1], row_next[args.met2]
            segmentations_next = [segmentations_next[i] for i in method_idx]
            p_next, uid_next = run_freeview(args.diff_maps, subject_id_next, image_next, segmentations_next[0], segmentations_next[1], center_next, freesurfer_path, xdotool_installed)


        labeling_start = time.time()

        #print(uid, uid_next)

        if xdotool_installed:
            time.sleep(0.5)
            show_window_command = f'xdotool windowmap $(xdotool search --name "UID: {uid}")'
            #print(show_window_command)
            subprocess.run(show_window_command, shell=True)#, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
        best, confidence, difference_strength, fail, comment = question_loop([p, p_next], methods)

        # sanitize comments field
        comment = comment.replace(',', ';')

        # log time
        label_time = time.time() - labeling_start

        # terminate freeview process
        if sys.platform == "darwin": # OS X
            # this is necessary because freeview launches two processes in MacOS
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
        else:
            p.send_signal(signal.SIGTERM)
            if xdotool_installed:
                window_close_command = f'xdotool search --name "UID: {uid}" windowclose'
                #print(window_close_command)
                subprocess.run(window_close_command, shell=True)

        already_labeled += 1



        with open(args.result, mode='a', newline='') as results_file:
            results_file.write(f"{row['ID']},{methods[0]},{methods[1]},{best},{confidence},{difference_strength},{fail},{comment},{args.user},{label_time},{num_differences}\n")

        print(f'[INFO] Labled {already_labeled}/{num_subjects} cases')


    print(f'[INFO] All cases have been labeled. Terminating...')
