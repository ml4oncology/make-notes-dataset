#!/usr/bin/python -u
import tempfile
import os
import sys
import time

# determine host
host = os.uname()[1]

# get temp file
fname = tempfile.mkstemp()
fname = fname[1]
ffname = fname.split('/')
ffname = ffname[-1]

# get system parameters
pwd = os.getcwd()
userName = sys.argv[1]
memory = sys.argv[2]
condaEnv = sys.argv[3]
nGPU = sys.argv[4]
mcmd = sys.argv[5:]

os.environ['PATH'] = '/usr/local/slurm/bin:/usr/local/bin:/usr/bin:/usr/local/sbin:/usr/sbin:/cluster/home/' + userName + '/.local/bin:/cluster/home/' + userName + '/bin'

# create a log directory
try:
    os.mkdir( pwd + '/log_files' )
except:
    pass

ADDSLURM = ''
if(host == 'voyager'):
    # change home to master
    pwd = '/master' + pwd
    ADDSLURM += '#SBATCH --cpus-per-task=2\n'
    ADDSLURM += 'export OMP_NUM_THREADS=2\n'
if(host == 'mac-login-amd'):
    ADDSLURM += '#SBATCH --partition=bdz'

fp = open(fname, 'w')
fp.write('#!/bin/bash\n\n')
fp.write('#SBATCH -o ' + pwd + '/log_files/log_' + ffname + '.txt\n')
fp.write('#SBATCH -D ' + pwd + '\n')
fp.write('#SBATCH -J py\n')
fp.write('#SBATCH --get-user-env\n')
fp.write('#SBATCH --ntasks=1\n')
fp.write('#SBATCH --mem=' + memory + 'GB\n')
fp.write('#SBATCH --time=0-01:00:00\n')
if int(nGPU) > 0:
    fp.write('#SBATCH --partition=gpu\n')
    fp.write('#SBATCH --account=gliugroup_gpu\n')
    fp.write('#SBATCH --gres=gpu:'+ nGPU +'\n')
else:
    fp.write('#SBATCH -p all')
fp.write(ADDSLURM)
fp.write('\n')

fp.write('module load python3\n')
for i in range(len(mcmd)):
    if(i + 1 == len(mcmd)):
        fp.write( condaEnv + ' -u ' + mcmd[i] + '\n\n')
    else:
        fp.write( condaEnv + ' -u ' + mcmd[i] + '&\n\n')
fp.close()

fp = open(fname, 'r')
print('--- BEGIN SLURM ---')
for l in fp:
    print(l),
print('--- END SLURM ---')
x = 'y'
time.sleep(3)
if(x == 'y'):
    os.system('/usr/local/slurm/bin/sbatch ' + fname)
