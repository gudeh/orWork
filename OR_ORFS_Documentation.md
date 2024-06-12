<!-----



Conversion time: 1.156 seconds.


Using this Markdown file:

1. Paste this output into your source file.
2. See the notes and action items below regarding this conversion run.
3. Check the rendered output (headings, lists, code blocks, tables) for proper
   formatting and use a linkchecker before you publish this page.

Conversion notes:

* Docs to Markdown version 1.0β36
* Tue Jun 11 2024 18:25:19 GMT-0700 (PDT)
* Source doc: OR & ORFS Documentation
----->


This document was prepared by Augusto Berndt, starting from an initial version by Eder Monteiro, and with assistance from Arthur Koucher during the review process. It was crafted based on my practical experiences as a new hire and my understanding of the subject matter. The primary aim is to support fellow new hires. However, it's important to note that there might be errors or misunderstandings in certain sections. Your feedback and suggestions for improvement are greatly appreciated.

**The Documentation**



* Internal documentation: [https://github.com/The-OpenROAD-Project-private/internal-documentation](https://github.com/The-OpenROAD-Project-private/internal-documentation) 
* ORFS:
    *  [https://openroad-flow-scripts.readthedocs.io/en/latest/](https://openroad-flow-scripts.readthedocs.io/en/latest/)
* OR: 
    * [https://openroad.readthedocs.io/en/latest/](https://openroad.readthedocs.io/en/latest/)
    * [https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/docs](https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/docs)

**The basics**



* Two main repositories
    * OpenROAD: [https://github.com/The-OpenROAD-Project/OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD)
    * OpenROAD-flow-scripts: [https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts)
* Contributions are made based on repository forks and pull requests
    * For this first task, fork the OpenROAD repository in your git profile
    * Clone the OpenROAD repository to your machine:
        * git clone --recursive [https://github.com/The-OpenROAD-Project/OpenROAD.git](https://github.com/The-OpenROAD-Project/OpenROAD.git)
        * git submodule update --init --recursive
    * Add your fork as a remote:
        * git remote add my_fork [https://github.com/my_user/OpenROAD.git](https://github.com/my_user/OpenROAD.git)
    * You will have two remotes in your local copy of the repository
        * git remote -v → origin, my_fork
    * All your pushes should go to my_fork
    * Also, you need to create branches for your work
* Creating a new branch
    * Always create a branch based on the latest master branch
        * git fetch --all --prune
        * git checkout master (if you’re not in the master branch)
        * git pull origin master
        * git checkout -b &lt;branch_name>
    * After creating the new branch, you can start coding and committing the changes
        * git add &lt;modified_files>
        * git commit -s -m “&lt;commit message>”
            * Make sure to always include your signature, this is what the “-s” parameter does!
            * Commit message on the OR tool should start with an acronym of the tool being modified. For example if modifications are made in global placer the commit message should start with “_gpl:”_,such as “_gpl: this modifications does this and that._” This is not a requirement on ORFS.
    * Push your new branch to your fork
        * git push my_fork &lt;branch_name>
* To create a PR, use the GitHub interface 
    * It is also a good practice to include the tool acronym to the PR title.

**Security steps**



* To avoid bad words and other security-related problems, we have a repository that performs checks on every commit you create
    * Clone this repository: [https://github.com/The-OpenROAD-Project/security](https://github.com/The-OpenROAD-Project/security)
    * Then run: git config --local core.hooksPath _/path/to/security**/git/hooks_**
* C++ code has to be formatted in clang-format. For example, the following will format the code inplace:
    * _clang-format -i /src/gpl/src/replace.cpp_
* Use snake case for variables, and camel case for functions.

**Continuous Integration (CI)**

The OpenROAD Project has two pairs of main repositories. One pair is public and another is private. The private repository has the same code as the public one. The testing is performed with the assistance of Jenkins.



* Public: [https://github.com/The-OpenROAD-Project](https://github.com/The-OpenROAD-Project) 
    * Public testing will only be triggered if a PR is created.
    * OpenROAD: [https://github.com/The-OpenROAD-Project/OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD)
    * OpenROAD-flow-scripts: [https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts)
* Private: [https://github.com/The-OpenROAD-Project-private](https://github.com/The-OpenROAD-Project-private)
    * Private testing (Secure-CI) will be triggered without a PR, a push with a proper branch name (starting with **secure-&lt;branch_name>**) should initiate the Secure-CI.
    * OpenROAD: [https://github.com/The-OpenROAD-Project-private/OpenROAD](https://github.com/The-OpenROAD-Project-private/OpenROAD)
    * OpenROAD-flow-scripts: [https://github.com/The-OpenROAD-Project-private/OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project-private/OpenROAD-flow-scripts) 

Both pairs have their own set of tests to be performed when code is updated.



* **Secure-CI**:
    * The Secure-CI runs only on **ORFS in the** **private repository**, which runs all private and public designs.
    * It is costly to run the Secure-CI and should not be called naively constantly. There is a delay between pushes, so an incomplete push followed by another one, should trigger only the last one to run the secure-CI.
    * When we create a secure-branch, the CI runs 3 pipelines:
1. Runs all public designs. New hires usually only have access to this set.
2. Runs some private designs, basically the TSMC designs.
3. Runs the rest of the private designs. With the addition of Calibre to verify the DRCs. On this part, the designs are from gf12 and intel16. 
* **OR tests** run on Jenkins, although they need a PR to run.

**Failing tests:**



* When tests fail make sure to understand what is happening. Here are some situations and steps to follow:
    * If tests fail on the master branch (nightly build) the same way as they do on your branch, they should not be your fault.
    * Differentiate between actual impeditive errors from simpler metrics failing.
        * **Metrics fail:** happen when the run converges to the end, although some metrics metadata are not within the limiting range. This can be accessed at the end of the log file from the _/flow/test/test_helper.sh_ script, for example: _[ERROR] finish__timing__drv__hold_violation_count fail test: 133.0 &lt;= 100.0_.
            * This metadata report is achieved with the command _make metadata_,included in the _test_helper.sh_ script.
            * When metrics metadata fail  you should check the values, if the difference is controlled, we usually update the metrics along the code modifications. This document contains further instructions on metrics update.
        * **Impeditive errors: **are the ones that do not allow the run to reach the end, such as segmentation faults, or failings during unit tests.

             


**Testing all public and private designs (secure-CI)**



* Some instructions can be found here: https://github.com/The-OpenROAD-Project-private/internal-documentation/blob/master/secure-ci.md
* Push the branch you want to test to the repository The-OpenROAD-Project-private/OpenROAD
* Create a **secure-&lt;branch_name>** branch on the repository The-OpenROAD-Project-private/OpenROAD-flow-scripts
* Update the submodule under tools/OpenROAD to the branch you created in the first step
* Push these updates to the private flow scripts repository and check the results in the

public Jenkins

**Moving forward to merge changes**

Commonly we first merge a PR on OR, generally following these steps:



1. Create a PR for OR.
    1. If regression test fail update on this branch using _save_flow_metrics_ and _save_flow_metrics_limits_.
2. Run a secure-CI for this OR PR.
    2. If we get a small fail in the metrics, we can just update that metric, for that we’ll need an ORFS PR that does two things:
        1. Update the metrics according to our changes in our OR PR.
        2. Points to the current commit in our OR PR (so that nightly public CI does not break).
3. Merge this OR PR.
4. Merge the ORFS PR.

**Dealing with regression tests results on OR**

The OR tool has regression tests located at _/tools/OpenRoad/test/_. For changes that generate new results, if a new correct result needs to be incorporated in the OR by updating the required files. 

For example, on one hand gpl might use regression tests that use metrics for actual designs as their results, within that context we would need to use the following scripts. On the other hand a different tool such as mpl2 might use just a def as a target result for the test, which would be updated by using the script _save_defok, save_ok_,and among others.

Use case of _save_flow_metrics_ and _save_flow_metrics_limits:_



* Download test results from artifacts tab in jenkins run: _/test/results.tgz_.
* Extract the files to /_tools/Openroad/test/results/_ for failing metric designs in the local directory. For example, if the failing design is _ibex/sky130hd_, you may unzip all files starting with _ibex_sky130hd_ in _/test/results/_ to the same path in your local directory.
    * **Alternatively **to these two previous steps, you can run locally to generate the required files.
* cd to _/tools/Openroad/test_, run _./save_flow_metrics \[design\]\_\[pdk\]_, for example: _./save_flow_metrics ibex_sky130hd_.
* Also run _./save_flow_metrics_limits \[design\]\_\[pdk\]_.
* You can check if modifications were performed with _git status_,and push them.

**Updating metrics on ORFS**

Updating metrics on ORFS is similar to OR, with some small differences:



* Download the report issue from the artifacts tab in the jenkins run of the secure-CI.
* Unzip the reports directory from the tar downloaded to the reports directory in your local /flow/reports/
* Use the command _make update_ok_ by setting the DESIGN_CONFIG file. For example:
    * _make DESIGN_CONFIG=./designs/asap7/jpeg/config.mk update_ok_
    * Check modified files with git status. They should be:
        * _flow/designs/asap7/jpeg/metadata-base-ok.json_ 
        * _flow/designs/asap7/jpeg/rules-base.json_

**Unit test**

We are currently in the process of switching from a TCL to C++ format with unit tests. The following tools have C++ tests under work already: DRT, ODB, and DFT.

Here are some general steps to create a new unit test following the older format with TCL. Each tool should have existing examples of unit tests, for example with gpl in  _toosl/OpenROAD/src/gpl/test_ directory. A unit test can be created by creating a way to execute a known error and make sure the tool does not crash. To do so one should:



* Have a .def file with the minimum possible information that reproduces the error.
* Have a .tcl file that will execute the tool with the .def file that reproduces the error
* To have the gold files, which are the .ok and .defok files

**Load and save runs on ORFS**



* Using **report_issue**:
    * SAVE: You can pack a run from your flow directory with the command:
        * _make DESIGN_CONFIG=./designs/nangate45/gcd/config.mk final_report_issue_
            * This creates a tar file with necessary files to run the design again in another directory or computer.
        * Alternatively you can generate a report issue for any other step other than the “final” step, for example: _make global_place_issue_. You can check the options by typing make and pressing tab a few times.
        * You may use _make clean_issues_, to remove files generated by the _report_issue_.
    * LOAD: You can load a run by unpacking the report_issue in a flow directory and use the following command:
        * _./run-me-gcd-nangate45-base.sh_ (this is useful to replicate a specific step)
            * You can also add the -gui parameter inside the run-me bash script.
        * Or do _source vars-gcd-nangate45-base.sh_,and use the _make_ command normally.
* Using **ODB** files.
    * SAVE: You can also export a run by saving the ODB file.
    * LOAD: And load the run with the ODB file: you can open the tool with _openroad -gui_, and load the ODB file with the _read_odb_ command, this can also be done on the gui (with the mouse) going in File→open DB, then selecting the ODB file.
        * ODB files are usually located at _/flow/results/nangate45/gdc/base._
* Usually each tool step has a debugger option. To run it you can add the command to the script file of the tool.
* There is a script to unpack multiple packages.

**Clean runs on ORFS**

**make clean_issue**- removes files generated by the report_issue command

**make clean_metadata**- removes the metadata resulting files generated by a run. This clean is tied to a single design run.

**make clean_all**- removes files generated by a run in the directories: logs, reports, results. This clean is tied to a single design run.

**make nuke**- removes all runs of all designs from the flow directory.

**Debug mode**



* Usually the ools have a debugger mode, for example, GPL can show iteratively the instances moving to their places in the core area. You can find instructions on the README file of each step tool, for example GPL has instructions for the debugger mode in _/tools/OpenROAD/src/gpl/README.md_. You can also investigate on the swig file for the tool in a file ending with _.i_ for example: _/tools/OpenROAD/src/gpl/replace.i_. 
    * It is recommended to use report_issue method to load the design and add -gui to run-me to use the debugger mode. The debugger mode usually interacts with the gui, so you need to make sure to run the tool with the -gui command somehow.

**Gcloud**



* Install: [https://cloud.google.com/sdk/docs/install](https://cloud.google.com/sdk/docs/install) 
* Login with email given.
* **Public VM:**
    * _gcloud compute ssh myUser-1_
        * If it asks for the project name: foss-fpga-tools-ext-openroad
* **Secure VM:**
    * _gcloud --project=openroad-tools-gf12 compute ssh secure-user-myUser_
    * Quick reminders:
        * Only clone and push to The-OpenROAD-Project-Private.
        * Do not download ***any*** data from secure machines.
* **To use the GUI:**
    * Add the following to the command _gcloud compute ssh_ → “-- -L 5901:localhost:5901”
    * Inside the server: 
        * _vncserver -geometry 1920x1080 :1_
        * Tip: do not use the same password for view-only, or don’t even set a view-only password.
    * In the client you can use tigerVNC:
        * _xtigervncviewer -SecurityTypes VncAuth :1_
    * Might be useful to use an alias for these commands.

**GDB on OR**



* To use gdb:
    * Go to _cd tools/OpenROAD/build._
        * Create build if non-existing: _mkdir build; cd build._
    * Run _cmake .. -DCMAKE_BUILD_TYPE=DEBUG_
    * Build with _make -j &lt;THERAD_COUNT>_
    * This is to make ORFS use the constructed binary:
        * _cp src/openroad ../../install/OpenROAD/bin_
    * _cd src_
    * _gdb openroad_
    * _run_
    * _gui::show_

**Extra**



* Swig files (ending with .i) are responsible for interfacing between TCL commands and C++ code, such as between ORFS and OR. 
* On Jenkins blue ocean, after a run is finished, you can go to artifacts and click on the Report, which has a summary with processed and organized information about the run.
* You can use _sudo ./etc/DependencyInstaller.sh_, this will install the necessary packages on _/usr/bin/._ This might be required to use multiple ORFS repositories on the same computer.
* Use environment variable _make FLOW_VARIANT=\[string\]_ to save ORFS results in a directory called _string_, instead of the “base” default directory name.
* Select certain instances on the GUI: _select -type Inst -filter {Description=Sequential cell}_ or _{Description=Macro}._ [More info here](https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/src/gui#select-objects).
* To make sure you run the same version of secure-CI locally. Check the ORFS commit hash in jenkins versus yours with git log. Check OR version on a log file in jenkins versus yours locally. Build using: _./build_openroad --local_
* You can change the location of an instance from the DEF file.
