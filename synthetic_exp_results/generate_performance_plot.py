import matplotlib.pyplot as plt 
import numpy as np
import os
import argparse

def file_to_list(file_path):
    with open(file_path) as file:
        lines = [line.strip() for line in file]
    return lines

def get_separation(lines):
    for line in lines:
        if "BEST SEPARATION" in line:
            sep = line[17:20]
            return float(sep)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--dir_num', type=str, help='dir num', required=True)
    args = parser.parse_args()
    dir_num = args.dir_num
    print(f"DIR NUM {dir_num}")
    x = os.listdir(f'/hdd2/dyah/uncorrelated_coloredmnist_synthetic_{str(dir_num)}')
    x = np.asarray(x)
    x = np.sort(x)

    log_dirs = [os.path.join("../","log", "SPURIOUS_NEW", "Synthetic_ColoredMNIST", str(frac)) for frac in x]
    last_dirs = []
    for dir_ in log_dirs:
        subdir = os.listdir(dir_)
        subdir = [os.path.join(dir_, subdir_) for subdir_ in subdir]
        subdir.sort(key=lambda x: os.path.getmtime(x))
        last_dirs.append(subdir[int(dir_num)])

    y_weight = []
    y_no_weight= []
    separation = []
    for dir_ in last_dirs:
        log_file = os.path.join(dir_, "log.txt")
        file_lines = file_to_list(log_file)
        y_weight_ = float(file_lines[-1][-5:])
        y_no_weight_ = float(file_lines[-11][-5:])
        separation_ = get_separation(file_lines)
        y_weight.append(y_weight_)
        y_no_weight.append(y_no_weight_)
        separation.append(separation_)

    plt.plot(x, y_no_weight, label="no weight")
    plt.plot(x, y_weight, label="with weight")
    plt.plot(x, separation, label="separation")
    plt.xlabel("spurious_p")
    plt.ylabel("%")
    plt.tight_layout()
    plt.legend()
    plt.savefig(f"uncorrelated_low_CB_range/acc_sep_{str(dir_num)}.png")