
# OR & ORFS Documentation

This document was prepared by **Augusto Berndt**, starting from an initial version by **Eder Monteiro** and with assistance from **Arthur Koucher** during the review process. It was crafted based on practical experiences as a new hire and an understanding of the subject matter. The primary aim is to support fellow new hires. However, it's important to note that there might be errors or misunderstandings in certain sections. Your feedback and suggestions for improvement are greatly appreciated.

## Documentation Links

- Internal documentation: [GitHub - The OpenROAD Project-private/internal-documentation](https://github.com/The-OpenROAD-Project-private/internal-documentation)
- ORFS Documentation: [ReadTheDocs - OpenROAD-flow-scripts](https://openroad-flow-scripts.readthedocs.io/en/latest/)
- OR Documentation:
  - [ReadTheDocs - OpenROAD](https://openroad.readthedocs.io/en/latest/)
  - [GitHub - OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD/tree/master/docs)

## The Basics

- **Repositories**:
  - OpenROAD: [GitHub - OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD)
  - OpenROAD-flow-scripts: [GitHub - OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts)

### Contribution Workflow

1. **Fork and Clone**:
   - Fork the OpenROAD repository to your GitHub profile.
   - Clone the repository:
     ```bash
     git clone --recursive https://github.com/The-OpenROAD-Project/OpenROAD.git
     git submodule update --init --recursive
     ```
   - Add your fork as a remote:
     ```bash
     git remote add my_fork https://github.com/my_user/OpenROAD.git
     ```
   - Verify remotes:
     ```bash
     git remote -v
     ```

2. **Branching**:
   - Create a branch based on the latest master branch:
     ```bash
     git fetch --all --prune
     git checkout master
     git pull origin master
     git checkout -b <branch_name>
     ```
   - Commit changes:
     ```bash
     git add <modified_files>
     git commit -s -m "<commit message>"
     ```
   - Push the new feedback and suggestions for im branch to your fork:
     ```bash
     git push my_fork <branch_name>
     ```

3. **Pull Request (PR)**:
   - Create a PR using the GitHub interface.

### Security Steps

- Clone the security repository:
  ```bash
  git clone https://github.com/The-OpenROAD-Project/security
  git config --local core.hooksPath /path/to/security/git/hooks
  ```
- Format C++ code using clang-format:
  ```bash
  clang-format -i /src/gpl/src/replace.cpp
  ```

### Continuous Integration (CI)

- **Public Repositories**:
  - [GitHub - The OpenROAD Project](https://github.com/The-OpenROAD-Project)
  - [GitHub - OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD)
  - [GitHub - OpenROAD-flow-scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts)

- **Private Repositories**:
  - [GitHub - The OpenROAD Project-private](https://github.com/The-OpenROAD-Project-private)
  - [GitHub - OpenROAD-private](https://github.com/The-OpenROAD-Project-private/OpenROAD)
  - [GitHub - OpenROAD-flow-scripts-private](https://github.com/The-OpenROAD-Project-private/OpenROAD-flow-scripts)

### Testing

- **Failing Tests**:
  - Understand the cause of failing tests.
  - Differentiate between actual errors and metrics failure.

- **Secure-CI**:
  - Run tests for all public and private designs.
  - Check the results on Jenkins.

### Merging Changes

- Merge PRs on OR after passing regression tests.
- Update metrics accordingly if there are minor discrepancies.

### Unit Testing

- **Current Status**:
  - Switching from TCL to C++ format.
  - Create new tests or update existing tests as needed.

### Debug Mode

- Instructions on using the debugger mode are available in each tool's README file.

### Gcloud and GDB

- Setup and use Gcloud for managing cloud resources.
- Use GDB for debugging applications.
