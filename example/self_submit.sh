#!/bin/bash
#PBS -P insert_your_project_here
#PBS -lncpus=1
#PBS -q normal
#PBS -lmem=100mb
#PBS -lwalltime=1:00
#PBS -v NJOBS,NJOB
#PBS -l wd
  
# =============================================================================
#  Self resubmitting PBS bash script:
#
#  * Submits a followon job before executing the current job.  The followon 
#    job will be in the "H"eld state until the current job completes
#
#  * Assumes program being run is checkpointing at regular intervals and is
#    able to resume execution from a checkpoint
#
#  * Does not assume the program will complete within the requested time
#
#  * Uses an environment variable (NJOBS) to limit the total number of 
#    resubmissions in the sequence of jobs
#
#  * Allows the early termination of the sequence of jobs - just create/touch
#    the file STOP_SEQUENCE in the jobs working directory.  This may be done 
#    by the executable program when it has completed the "whole" job or by hand 
#    if there is a problem
#
#  * This script may be renamed anything (<15 characters) but if you use the -N 
#    option to qsub you must edit the qsub line below to give the script name 
#    explicitly
#
#  * To use: 
#         - make appropriate changes to the PBS options above and to the 
#           execution and file manipulation lines belo
#         - submit the job with the appropriate value of NJOBS, eg:
#                    qsub -v NJOBS=5 <scriptname>
#
#  * To kill a job sequence, either touch the file STOP_SEQUENCE or qdel
#    the held job followed by the running job
#
#  * To test, try  "sleep 100"  as your executable line
#
# ===============================================================================

ECHO=/bin/echo

#
# These variables are assumed to be set:
#   NJOBS is the total number of jobs in a sequence of jobs (defaults to 1)
#   NJOB is the number of the previous job in the sequence (defaults to 0)
#
  
if [ X$NJOBS == X ]; then
    $ECHO "NJOBS (total number of jobs in sequence) is not set - defaulting to 1"
    export NJOBS=1
fi
  
if [ X$NJOB == X ]; then
    $ECHO "NJOB (previous job number in sequence) is not set - defaulting to 0"
    export NJOB=0
fi

#
# Quick termination of job sequence - look for a specific file 
#  (the filename could be a qsub -v argument)
#
if [ -f STOP_SEQUENCE ]; then
    $ECHO  "Terminating sequence after $NJOB jobs"
    exit 0
fi

#
# Increment the counter to get current job number
#
NJOB=$(($NJOB+1))

#
# Are we in an incomplete job sequence - more jobs to run ?
#
if [ $NJOB -lt $NJOBS ]; then
    #
    # Now submit the next job
    # (Assumes -N option not used to change job name.)
    #
    NEXTJOB=$(($NJOB+1))
    $ECHO "Submitting job number $NEXTJOB in sequence of $NJOBS jobs"
    qsub -z -W depend=afterany:$PBS_JOBID $PBS_JOBNAME
else
    $ECHO "Running last job in sequence of $NJOBS jobs"
fi


#
# File manipulation prior to job commencing, eg. clean up previous output files,
# check for consistency of checkpoint files, ...
#
if [ $NJOB -gt 1 ]; then
    echo " "
    # .... USER INSERTION HERE 
fi


#
# Now run the job ...
#

#===================================================
# .... USER INSERTION OF EXECUTABLE LINE HERE 
#===================================================

  
#
# Not expected to reach this point in general but if we do, check that all 
# is OK.  If the job command exited with an error, terminate the job
#
errstat=$?
if [ $errstat -ne 0 ]; then
    # A brief nap so PBS kills us in normal termination. Prefer to 
    # be killed by PBS if PBS detected some resource excess
    sleep 5  
    $ECHO "Job number $NJOB returned an error status $errstat - stopping job sequence."
    touch STOP_SEQUENCE
    exit $errstat
fi
