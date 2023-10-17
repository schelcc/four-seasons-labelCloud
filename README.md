# Four Seasons modified labelCloud
Here you will find instructions for the installation and labelling processes. However, this only has the labelCloud code -- you need the full zipped download if you don't already have it. If you need it, ask your lead for it.

**Warning - This has been difficult to get running on Macs. There are added instructions, but you are likely to run into issues if you are on MacOS.**

---

## Installation
As mentioned, first ensure you've downloaded and extracted the full zip. In your terminal, navigate to wherever you extracted it to.

You'll need to use Python 3.8 for labelCloud, which is no longer the standard Python version on most systems. To handle for this, we'll create a Conda environment, allowing us to operate in a separate env that is in Python 3.8 (this is sort of like how we use Docker for all of our ROS development).

To start, you'll want to grab the [Miniconda](https://docs.conda.io/projects/miniconda/en/latest/) version for your system. Follow the steps on their site to install it.
After installation, you can verify Conda is properly installed and set up by executing ``conda info``. If your installation was succesful, you should see a readout of various information:

```
     active environment : base
    active env location : $HOME/miniconda3
            shell level : 1
       user config file : $HOME/.condarc
 populated config files : 
          conda version : 23.5.2
    conda-build version : not installed
         python version : 3.11.4.final.0
       virtual packages : __archspec=1=x86_64
                          __glibc=2.35=0
                          __linux=6.2.0=0
                          __unix=0=0
       base environment : $HOME/miniconda3  (writable)
      conda av data dir : $HOME/miniconda3/etc/conda
  conda av metadata url : None
           channel URLs : https://repo.anaconda.com/pkgs/main/linux-64
                          https://repo.anaconda.com/pkgs/main/noarch
                          https://repo.anaconda.com/pkgs/r/linux-64
                          https://repo.anaconda.com/pkgs/r/noarch
          package cache : $HOME/miniconda3/pkgs
                          $HOME/.conda/pkgs
       envs directories : $HOME/miniconda3/envs
                          $HOME/.conda/envs
               platform : linux-64
             user-agent : conda/23.5.2 requests/2.29.0 CPython/3.11.4 Linux/6.2.0-34-generic ubuntu/22.04.3 glibc/2.35
                UID:GID : 1000:1000
             netrc file : None
           offline mode : False
```

> This printout is on a linux system -- if you're on something else, it may appear different. The gist should be the same, and it executing w/o error is the most important thing.

The most important part to note about the above info is the first line, ``active environment``.
This denotes the Conda environment you are currently in. It should say ``base`` directly after installation. Some systems will show the active env right on your command prompt, but in case it doesn't that is how you can check. 

Now create the environment we'll use to run our labelling software:
```
conda create -n <name> python=3.8 
```
Feel free to name the env as you please, just note the name you choose. Going forward we'll refer to it as 'label', but that is an arbitrary choice. If you name it something different, you'll just need to swap 'label' for your selected name.

Now enter the environment by executing:
```
conda activate label
```
You should now be in your env for the labelling software. Anything you do related to python is now specific to this environment, and is done in terms of Python 3.8.

Now we're going to replace the labelCloud you downloaded earlier with the updated one found here. Go ahead and delete the ``labelCloud_V2`` directory the download should've come with, and replace it with this repository. We're going to clone it as a git repo to ensure that we keep it tied to this repository -- there may be changes in the future. You should now be in the directory you extracted the zipped contents, and there should be no ``labelCloud`` (because you deleted it). You can now clone this repository via:
```
git clone https://github.com/schelcc/four-seasons-labelCloud.git
```
Or however else you see fit (e.g. via ssh instead). This may take a second, so don't kill it if it seems to hang. After it's fully cloned, you can verify you did it right by navigating inside it and executing
```
git status
```
If you get an error, something's not right. If you don't you're good to move on.

For the final step here, we're going to install the required packages. To do this, ensure you're in the environment you created and you've navigated inside of the repository you just cloned. Once you've ensured as such, run:
```
pip install -r requirements.txt
```
This should run without error, and if it does then you are properly set up! If there were errors, reach out to your lead for assistance.

---

## Labelling Procedure
