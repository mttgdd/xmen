#!/usr/bin/env python3
"""A module holding the ExperimentManager implementation. The module can also be run activating the
experiment managers command line interface"""

#  Copyright (C) 2019  Robert J Weston, Oxford Robotics Institute
#
#  xmen
#  email:   robw@robots.ox.ac.uk
#  github: https://github.com/robw4/xmen/
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  You should have received a copy of the GNU General Public License
#   along with this program. If not, see <http://www.gnu.org/licenses/>.
import sys
import os
import datetime
import time
import glob

from xmen.utils import get_meta, get_version, DATE_FORMAT, get_git
import xmen.config


class ExperimentNotFoundException(Exception):
    def __init__(self, root, name):
        self.root = root
        self.name = name

    def __repr__(self):
        return f"The experiment {self.name} was not found under root {self.root}."


class InvalidExperimentRoot(Exception):
    def __init__(self, root):
        self.root = root

    def __repr__(self):
        return f"The folder {self.root} is not a valid experiment root. It has either" \
               f"not been initilaised or is missing a defaults.yml and / or run.sh script"


class ExperimentManager(object):
    """A helper class with wrapped command line interface used to manage a set of experiments. It is compatible both
    with experiments generated by the ``Experiment.to_root`` method call as well as any experiment that can be
    represented as a bash `script.sh` which takes a set of parameters in a yaml file as input.

    More Info:
        At its core the experiment manager maintains a single `root` directory::

            root
            ├── defaults.yml
            ├── experiment.yml
            ├── script.sh
            ├── {param}:{value}__{param}:{value}
            │   └── params.yml
            ├── {param}:{value}__{param}:{value}
            │   └── params.yml
            ...

        In the above we have:

            * ``defaults.yml`` defines a set of parameter keys and there default values shared by each experiment. It
              generated from the ``Experiment`` class it will look like::

                  # Optional additional Meta parameters
                  _created: 06:58PM September 16, 2019    # The date the defaults were created
                  _version:
                      module: /path/to/module/experiment/that/generated/defaults/was/defined/in
                      class: TheNameOfTheExperiment
                      git:
                         local: /path/to/git/repo/defaults/were/defined/in
                         branch: some_branch
                         remote: /remote/repo/url
                         commit: 80dcfd98e6c3c17e1bafa72ee56744d4a6e30e80    # The git commit defaults were generatd at

                  # Default parameters
                  a: 3 #  This is the first parameter (default=3)
                  b: '4' #  This is the second parameter (default='4')

               The ``ExperimentManager`` is also compatible with generic experiments. In this the ``_version`` meta
               field can be added manually, replacing ``module`` and ``class`` with ``path``. The git information for
               each will be updated automatically provided ``path`` is within a git repository.

            * ``script.sh`` is a bash script. When run it takes a single argument ``'params.yml'`` (eg. ```script.sh params.yml```).

                .. note ::

                    ``Experiment`` objects are able to automatically generate script.sh files that look like this::

                        #!/bin/bash
                        # File generated on the 06:34PM September 13, 2019
                        # GIT:
                        # - repo /path/to/project/module/
                        # - remote {/path/to/project/module/url}
                        # - commit 51ad1eae73a2082e7636056fcd06e112d3fbca9c

                        export PYTHONPATH="${PYTHONPATH}:path/to/project"
                        experiments /path/to/project/module/experiment.py --execute ${1}

              Generic experiments are compatible with the ``ExperimentManager`` provided they can be executed with a
              shell script. For example a bash only experiment might have a ``script.sh`` script that looks like::

                   #!/bin/bash
                   echo "$(cat ${1})"

            * A set of experiment folders representing individual experiments within which each experiment has a
              ``params.yml`` with a set of override parameters changed from the original defaults. These overrides define the
              unique name of each experiment (in the case that multiple experiments share the same overrides each experiment
              folder is additionally numbered after the first instantiation). Additionally, each ``params.yml`` contains the
              following::

                    # Parameters special to params.yml
                    _root: /path/to/root  #  The root directory to which the experiment belongs (should not be set)
                    _name: a:10__b:3 #  The name of the experiment (should not be set)
                    _status: registered #  The status of the experiment (one of ['registered' | 'running' | 'error' | 'finished'])
                    _created: 07:41PM September 16, 2019 #  The date the experiment was created (should not be set)
                    _purpose: this is an experiment example #  The purpose for the experiment (should not be set)
                    _messages: {} #  A dictionary of messages which are able to vary throughout the experiment (should not be set)

                    # git information is updated at registration if ``_version['module']`` or `_version['path']``
                    # exists in the defaults.yml file and the path is to a valid git repo.
                    _version:
                        module: /path/to/module   # Path to module where experiment was generated
                        class: NameOfExperimentClass     # Name of experiment class params are compatible with
                        git: #  A dictionary containing the git history corresponding to the defaults.yml file. Only
                          local_path: path/to/git/repo/params/were/defined/in
                          remote_url: /remote/repo/url
                          hash: 80dcfd98e6c3c17e1bafa72ee56744d4a6e30e80
                                        # Parameters from the default (with values overridden)
                    a: 3 #  This is the first parameter (default=3)
                    b: '4' #  This is the second parameter (default='4')

            * ``experiment.yml`` preserves the experiment state with the following entries::

                    root: /path/to/root
                    defaults: /path/to/root/defaults.yml
                    script: /path/to/root/script.sh
                    experiments:
                    - /private/tmp/new-test/a:10__b:3
                    - /private/tmp/new-test/a:20__b:3
                    - /private/tmp/new-test/a:10__b:3_1
                    overides:
                    - a: 10
                      b: '3'
                    - a: 20
                      b: '3'
                    - a: 10
                      b: '3'
                    created: 07:41PM September 16, 2019   # The date the experiment manager was initialised

        The ``ExperimentManager`` provides the following public interface for managing experiments:

            * ``__init__(root)``:
                Link the experiment manager with a root directory and load the experiments.yml if it exists
            * ``initialise(script, defaults)``:
                Initialise an experiment set with a given script and default parameters
            * ``link(string_pattern)``:
                Register a number of experiments overriding parameters based on the particular ``string_pattern``
            * ``list()``:
                 Print all the experiments and their associated information
            * ``unlink(pattern)``:
                 Relieve the experiment manager of responsibility for all experiment names matching pattern
            * ``clean()``:
                 Delete any experiments which are no longer the responsibility of the experiment manager
            * ``run(string, options)``:
                 Run an experiment or all experiments (if string is ``'all'``) with options prepended.

        Example::

            experiment_manager = ExperimentManager(ROOT_PATH)   # Create experiment set in ROOT_PATH
            experiment_manager.initialise(PATH_TO_SCRIPT, PATH_TO_DEFAULTS)
            experiment_manager.link('parama: 1, paramb: [x, y]')      # Register a set of experiments
            experiment_manger.unlink('parama_1__paramb_y')                # Remove an experiment
            experiment_manager.clean()                                    # Get rid of any experiments no longer managed
            experiment_run('parama:1__paramb:x', sh)                      # Run an experiment
            experiment_run('all')                                         # Run all created experiments
        """

    def __init__(self, root="", headless=False):
        """Link an experiment manager to root. If root already contains an ``experiment.yml`` then it is loaded.

        In order to link a new experiment with a defaults.yml and script.sh file then the initialise method must be
        called.

        Args:
            root: The root directory within which to create the experiment. If "" then the current working directory is
                used. If the root directory does not exist it will be made.

        Parameters:
            root: The root directory of the experiment manger
            defaults: A path to the defaults.yml file. Will be None for a fresh experiment manager (if experiments.yml
                has just been created).
            script: A path to the script.sh file. Will be None for a fresh experiment manager (if experiments.yml
                has just been created).
            created: A string giving the date-time the experiment was created
            experiments: A list of paths to the experiments managed by the experiment manager
            overides: A list of dictionaries giving the names (keys) and values of the parameters overridden from the
                defaults for each experiment in experiments.
            notes: A set of notes attched to the experiment set
            purpose: The purpose of the epxeriment
        """
        self.root = os.getcwd() if root == "" else os.path.abspath(root)
        if not os.path.isdir(self.root):
            os.makedirs(self.root)
        self.defaults = None
        self.script = None
        self.experiments = []
        self.overides = []
        self.created = None
        self.purpose = None
        self.notes = []
        self.type = None
        self._specials = ['_root', '_name', '_status', '_created', '_purpose', '_messages', '_version', '_meta']
        if not headless:
            self._config = xmen.config.Config()
        else:
            self._config = None

        # Load dir from yaml
        if os.path.exists(os.path.join(self.root, 'experiment.yml')):
            self._from_yml()

    def check_initialised(self):
        """Make sure that ``'experiment.yml'``, ``'script.sh'``, ``'defaults.yml'`` all exist in the directory"""
        all_exist = all(
            [os.path.exists(os.path.join(self.root, s)) for s in ['experiment.yml', 'script.sh', 'defaults.yml']])
        if not all_exist:
            raise InvalidExperimentRoot(self.root)

    def load_defaults(self):
        """Load the ``defaults.yml`` file into a dictionary"""
        import ruamel.yaml
        with open(os.path.join(self.root, 'defaults.yml'), 'r') as file:
            defaults = ruamel.yaml.load(file, ruamel.yaml.RoundTripLoader)
        return defaults

    def save_params(self, params, root):
        """Save a dictionary of parameters at ``{root}/{experiment_name}/params.yml``

        Args:
            params (dict): A dictionary of parameters to be saved. Can also be a CommentedMap from ruamel
            experiment_name (str): The name of the experiment
        """
        import ruamel.yaml
        with open(os.path.join(root, 'params.yml'), 'w') as out:
            yaml = ruamel.yaml.YAML()
            yaml.dump(params, out)

    def update_meta(self):
        """Save a dictionary of parameters at ``{root}/{experiment_name}/params.yml``

        Args:
            params (dict): A dictionary of parameters to be saved. Can also be a CommentedMap from ruamel
            experiment_name (str): The name of the experiment
        """
        import ruamel.yaml
        defaults = self.load_defaults()
        if '_meta' not in defaults:
            defaults.insert(2, '_meta', get_meta())
        else:
            defaults['_meta'] = get_meta()
        if '_home' in defaults:
            defaults.pop('_home')
        # experiment_path = os.path.join(self.root, experiment_name)

        with open(os.path.join(self.root, 'defaults.yml'), 'w') as out:
            yaml = ruamel.yaml.YAML()
            yaml.dump(defaults, out)

        for p in self.experiments:
            params = self.load_params(p)
            if '_meta' not in params:
                params.insert(7, '_meta', get_meta())
            else:
                params['_meta'] = get_meta()
            if '_home' in params:
                params.pop('_home')
            if '_origin' in params:
                params.pop('_origin')
            # if '_origin' not in params:
            #     params.insert(8, '_origin', params['_root'])
            self.save_params(params, os.path.basename(p))

    def load_params(self, experiment_path, experiment_name=False):
        """Load parameters for an experiment. If ``experiment_name`` is True then experiment_path is assumed to be a
        path to the folder of the experiment else it is assumed to be a path to the ``params.yml`` file."""
        import ruamel.yaml
        if experiment_name:
            experiment_path = os.path.join(self.root, experiment_path)
        with open(os.path.join(experiment_path, 'params.yml'), 'r') as params_yml:
            params = ruamel.yaml.load(params_yml, ruamel.yaml.RoundTripLoader)
        return params

    def _to_yml(self):
        """Save the current experiment manager to an ``experiment.yaml``"""
        import ruamel.yaml
        params = {k: v for k, v in self.__dict__.items() if k[0] != '_' or k in self._specials}
        with open(os.path.join(self.root, 'experiment.yml'), 'w') as file:
            ruamel.yaml.dump(params, file, Dumper=ruamel.yaml.RoundTripDumper)

    def _from_yml(self):
        """Load an experiment manager from an ``experiment.yml`` file"""
        import ruamel.yaml
        with open(os.path.join(self.root, 'experiment.yml'), 'r') as file:
            params = ruamel.yaml.load(file, ruamel.yaml.RoundTripLoader)
            self.root = params['root']
            self.defaults = params['defaults']
            self.script = params['script']
            self.created = params['created']
            self.experiments = params['experiments']
            self.overides = params['overides']
            if 'purpose' in params:
                self.purpose = params['purpose']
            if 'notes' in params:
                self.notes = params['notes']
            if 'type' in params:
                self.type = params['type']

    def initialise(self, *, defaults="", script="", purpose="", name=None):
        """Link an experiment manager with a ``defaults.yml`` file and ``sript.sh``.

        Args:
            defaults (str): A path to a ``defaults.yml``. If "" then a ``defaults.yml`` is searched for in the current
                work directory.
            script (str): A path to a ``script.sh``. If ``""`` then a script.sh file is searched for in the current work
                directory.
        """
        from shutil import copyfile
        print(name)
        if name is None:
            # Load defaults
            self.defaults = os.path.join(self.root, 'defaults.yml') if defaults == "" else os.path.abspath(defaults)
            print(f'Defaults from {self.defaults}')
            if os.path.exists(self.defaults):
                if defaults != "":
                    copyfile(self.defaults, os.path.join(self.root, 'defaults.yml'))
                    self.defaults = os.path.join(self.root, 'defaults.yml')
            else:
                raise ValueError(f"No defaults.yml file exists in {self.root}. Either use the root argument to copy "
                                 f"a default file from another location or add a 'defaults.yml' to the root directory"
                                 f"manually.")

            # Load script file
            self.script = os.path.abspath(os.path.join(self.root, 'script.sh')) if script == "" else os.path.abspath(script)
            print(f'Script from {self.script}')
            if os.path.exists(self.script):
                if script != "":
                    copyfile(self.script, os.path.join(self.root, 'script.sh'))
                    self.script = os.path.join(self.root, 'script.sh')
            else:
                raise ValueError(f"File {self.script} does not exist. Either use the script argument to copy "
                                 f"a script file from another location or add a 'script.sh' to the root directory"
                                 f"manually.")
            self.script = os.path.join(self.root, 'script.sh')
        else:
            if name not in self._config.python_experiments:
                print(f'Python Experiment {name} has not been registered with the global configuration. Aborting!')
                return

            # for p in self._config.python_paths:
            #     if self._config.python_experiments[name].startswith(p):
            #         # Inserted right at the start (will be the first one searched in)
            #         sys.path.insert(0, p)

            import subprocess
            subprocess.call([self._config.python_experiments[name], '--to_root', self.root])

            self.script = os.path.join(self.root, 'script.sh')
            self.defaults = os.path.join(self.root, 'defaults.yml')
            self.type = name

        # Meta Information
        self.created = datetime.datetime.now().strftime(DATE_FORMAT)

        # Save state to yml
        if os.path.exists(os.path.join(self.root, 'experiment.yml')):
            print(f"There already exists a experiment.yml file in the root directory {self.root}. "
                  f"To reinitialise an experiment folder remove the experiment.yml.")
            exit()
        print(f'Experiment root created at {self.root}')

        # Add purpose message
        if self._config.prompt:
            purpose = input('\nPlease enter the purpose of the experiments: ')
        self.purpose = purpose

        # Add experiment to global config
        self._to_yml()

    def _generate_params_from_string_params(self, x):
        """Take as input a dictionary and convert the dictionary to a list of keys and a list of list of values
        len(values) = number of parameters specified whilst len(values[i]) = len(keys).
        """
        import ruamel.yaml
        values = [[]]  # List of lists. Each inner list is of length keys
        keys = []

        for k, v in x.items():
            if type(v) is str:
                if '|' in v:
                    v = v.split('|')
                    v = [ruamel.yaml.load(e, Loader=ruamel.yaml.Loader) for e in v]
                else:
                    v = [v]
            else:
                v = [v]
            keys += [k]

            new_values = []
            # Generate values
            for val in values:  # val has d_type list
                for vv in v:  # vv has d_type string
                    # print(val, vv)
                    new_values += [val + [vv]]
            values = new_values
        return values, keys

    def note(self, pattern, msg, remove=False):
        """Add a note to experiments matching pattern. If remove is True msg is deleted instead."""
        self.check_initialised()
        experiments = [p for p in glob.glob(os.path.join(self.root, pattern)) if p in self.experiments]
        for root in experiments:
            import ruamel.yaml.comments
            params = self.load_params(root)
            if '_notes' not in params or params['_notes'] is None:
                params['_notes'] = []
            if not remove:
                params['_notes'] += [msg.strip()]
            else:
                from ruamel.yaml.comments import CommentedSeq
                if msg in params['_notes']:
                    params['_notes'].remove(msg)
                    if not params['_notes']:
                        params['_notes'] = None
                # params['_notes'] = CommentedSeq([n for n in params['_notes'] if msg.strip() != n])
            self.save_params(params, root)

    def replant(self, root):
        # Relink experiments under root
        if self.root != root:
            for i, p in enumerate(self.experiments):
                new_exp_path = os.path.join(root, os.path.basename(p))
                if not os.path.exists(new_exp_path):
                    raise ExperimentNotFoundException(root, os.path.basename(p))
                else:
                    self.experiments[i] = new_exp_path

        # Change the location of defaults and script.sh in experiment.yml
        self.defaults = self.defaults.replace(self.root, root)
        if not os.path.exists(self.defaults):
            raise FileNotFoundError(f'No defaults.yml file found in {root}')
        self.script = self.script.replace(self.root, root)
        if not os.path.exists(self.defaults):
            raise FileNotFoundError(f'No script.sh file found in {root}')

        # # Update global config
        # with self._config as config:
        #     entry = self._config.experiments.pop(self.root, None)
        #     if entry is not None:
        #         config.experiments[root] = entry
        #     else:  # We will need to do a bit more work
        #         # The experiment did not exist in the global configuration
        #         config.experiments[root] = {
        #             "created": self.created, "type": self.type, "purpose": self.purpose, "notes": self.notes}

        # Update params.yml file of each experiment
        self.root = root
        for i, path in enumerate(self.experiments):
            params = self.load_params(path)
            params["_root"] = root
            self.save_params(params, path)

        self._to_yml()

    def move(self, dest):
        """Move the current experiment set from one location to another."""
        dest = os.path.abspath(dest)
        if not os.path.exists(dest):
            os.makedirs(dest)

        # Do the move
        os.renames(self.root, dest)
        # self.root = dest
        self.replant(dest)

    def register(self, name=None, string_params=None, purpose='', header=None, shell='/bin/bash', repeats=1):
        """Register a set of experiments with the experiment manager.

        Experiments are created by passing a yaml dictionary string of parameters to overload in the ``params.yml``
        file. The special symbol ``'|'`` can be thought of as an or operator. When encountered each of the parameters
        either side ``'|'`` will be created separately with all other parameter combinations.

        Args:
            string_params (str): A yaml dictionary of parameters to override of the form
                ``'{p1: val11 | val12, p2: val2, p3: val2 | p4: val31 | val32 | val33, ...}'``.
                The type of each parameter is inferred from its value in defaults. A ValueError will be raised if any
                of the parameter cannot be found in defaults. Parameters can be float (1.), int (1), str (a), None, and
                dictionaries {a: 1., 2.} or lists [1, 2] of these types_match. None parameters are specified using empty space.
                The length of list parameters must match the length of the parameter in default.
                Dictionary parameters may only be partially defined. Missing keys will be assumed
                to take there default value.

                The special character '|' is used as an or operator. All combinations of parameters
                either side of an | operator will be created as separate experiments. In the example above
                ``N = 2 * 2 * 3 = 12`` experiments will be generated representing all the possible values for
                parameters ``p1``, ``p3`` and ``p4`` can take with ``p2`` set to ``val2`` for all.
            purpose (str): An optional purpose message for the experiment.
            header (str): An optional header message prepended to each run script.sh

        .. note ::

            This function is currently only able to link list or dictionary parameters at the first level.
            ``{a: {a: 1.. b: 2.} | {a: 2.. b: 2.}}`` works creating two experiments with over-ridden dicts in each case
            but ``{a: {a: 1. | 2.,  b:2.}}`` will fail.

            The type of each override is inferred from the type contained in the defaults.yml file (ints will be cast
            to floats etc.) where possible. This is not the case when there is an optional parameter that can take a
            None value. If None (null yaml) is passed as a value it will not be cast. If a default.yml entry is
            given the value null the type of any overrides in this case will be inferred from the yaml string.
        """
        # TODO: This function is currently able to link only arguments only at the first level
        import ruamel.yaml
        import importlib.util
        self.check_initialised()
        defaults = self.load_defaults()

        if name is None and string_params is None:
            raise ValueError('At least one of name and string params must be set')

        if string_params is not None:
            # Convert input string to dictionary
            p = ruamel.yaml.load(string_params, Loader=ruamel.yaml.Loader)
        else:
            p = {}

        values, keys = self._generate_params_from_string_params(p)

        # Add new experiments
        paths = []
        for elem in values:
            overides = {}
            for k, v in zip(keys, elem):
                if v is dict:
                    if defaults[k] is not dict:
                        raise ValueError(f'Attempting to update dictionary parameters but key {k} is not a dictionary'
                                         f'in the defaults.yml')
                    overides.update({k: defaults[k]})
                    for dict_k, dict_v in v.items():
                        if dict_k not in defaults[k]:
                            raise ValueError(f'key {dict_k} not found in defaults {k}')
                        overides[k].update({dict_k: dict_v})
                if v is list:
                    if defaults[k] is not list:
                        raise ValueError(f'Attempting to update a list of parameters but key {k} does not have '
                                         f'a list value')
                    if len(v) != len(defaults[k]):
                        raise ValueError(f'Override list length does not match default list length')
                    overides.update({k: [v[i] for i in range(len(v))]})
                else:
                    overides.update({k: v})

            # Check parameters are in the defaults.yml file
            if any([k not in defaults for k in overides]):
                raise ValueError('Some of the specified keys were not found in the defaults')

            if name is None:
                current_name = '__'.join([k + '=' + str(v) for k, v in overides.items()])
            else:
                current_name = name
            path = os.path.join(self.root, current_name)

            experiment_name = current_name
            experiment_path = path
            for _ in range(repeats):
                # Setup experiment folder
                if os.path.isdir(experiment_path):
                    for i in range(1, 100):
                        if not os.path.isdir(path + f"_{i}"):
                            # logging.info(f"Directory already exists creating. The current experiment will be set up "
                            #              f"at {experiment_path}_{i}")
                            experiment_name = current_name + f"_{i}"
                            experiment_path = path + f"_{i}"
                            break
                        if i == 99:
                            raise ValueError('The number of experiments allowed with the same overides is limited to 100')
                os.makedirs(experiment_path)

                # Convert defaults to params
                # definition = defaults['definition'] if 'definition' in defaults else None
                if defaults['_version'] is not None:
                    version = defaults['_version']
                    if 'path' in version:
                        version = get_version(path=version['path'])
                    elif 'module' in version and 'class' in version:
                        # We want to get version form the original class if possible
                        version = {
                            'module': defaults['_version']['module'],
                            'class': defaults['_version']['class'],
                            'git': get_git(path=defaults['_version']['module'])}
                else:
                    version = None

                meta = get_meta(get_conda=True)
                conda_env = meta.get('conda', None)
                if conda_env is not None and self._config:
                    from ruamel.yaml import YAML
                    yaml = YAML()
                    yaml.default_flow_style = False
                    with open(os.path.join(self.root, experiment_name, 'environment.yml'), 'w') as f:
                        yaml.dump(conda_env, f)

                from xmen.experiment import CONFIG, get_timestamps, get_time
                ts = get_time()
                extra_params = {
                    '_root': os.path.join(self.root, experiment_name),
                    '_status': 'registered',
                    '_purpose': self.purpose,
                    '_notes': None,
                    '_user': CONFIG.local_user,
                    '_host': CONFIG.local_host,
                    '_timestamps': get_timestamps(created=ts, registered=ts),
                    '_messages': {},
                    '_version': version,
                    '_meta': get_meta()}

                from copy import deepcopy
                params = deepcopy(defaults)
                # Remove optional parameters from defaults
                for k in ['_created', '_version', '_meta']:
                    if k in params:
                        params.pop(k)

                # Add base parameters to params
                # helps = get_attribute_helps(Experiment)
                from xmen.experiment import Experiment
                for i, (k, v) in enumerate(extra_params.items()):
                    h = Experiment._params[k][2]
                    params.insert(i, k, v, h)

                # Generate a script.sh in each folder that can be used to run the experiment
                if header is not None and header != '':
                    header_str = open(header).read()
                else:
                    header_str = self._config.header
                script = '\n'.join(
                    [f'#!{shell}\n{header_str}',
                     f'exec {shell} {os.path.join(self.script)} {os.path.join(experiment_path, "params.yml")}',
                     'echo EXPERIMENT FINISHED!']
                )
                with open(os.path.join(self.root, experiment_name, 'run.sh'), 'w') as f:
                    f.write(script)

                # Update the overridden parameters
                params.update(overides)
                self.save_params(params, experiment_name)
                self.experiments.append(experiment_path)
                self.overides.append(overides)
                paths += [experiment_path]

        self._config.link(paths)
        self._to_yml()

    def reset(self, pattern, status='registered'):
        """Update the status of the experiment. This is useful if you need to re-run an experiment
        from a latest saved checkpoint for example.

        Args:
            pattern: The experiment name
        """
        experiments = [p for p in glob.glob(os.path.join(self.root, pattern)) if p in self.experiments]
        for p in experiments:
            P = self.load_params(p)
            P['_status'] = status
            self.save_params(P, P['_root'])
        self._config.sync(experiments)

    def clean(self):
        """Remove directories no longer linked to the experiment manager"""
        from shutil import rmtree
        self.check_initialised()
        subdirs = [p for p in os.listdir(self.root) if os.path.isdir(p) and
                   os.path.exists(os.path.join(p, 'params.yml')) and
                   not any(e.endswith(p) for e in self.experiments)]
        if subdirs:
            if self._config.prompt:
                print('The following experiments were found for deletion:')
                for p in subdirs:
                    print(p)
                inp = input(f'Do you wish to continue? [y | n]: ')
                if inp != 'y':
                    print('Aborting!')
                    return
            print('The following experiments were deleted:')
            for d in subdirs:
                if os.path.exists(os.path.join(d, 'params.yml')):
                    rmtree(d)
                    print(d)
        else:
            print('no folders found for deletion')
        self._config.clean()

    def rm(self):
        from shutil import rmtree
        self.check_initialised()
        if self._config.prompt:
            inp = input(f'This command will remove the whole experiment folder {self.root}. '
                        f'Do you wish to continue? [y | n]: ')
            if inp != 'y':
                print('Aborting!')
                return
        rmtree(self.root)
        print(f'Removed {self.root}')
        self._config.clean()

    def run(self, pattern, *flags):
        """Run all experiments that match the global pattern using the run command given by args."""
        from subprocess import Popen
        options = set(flags)

        def call(*popenargs, timeout=None, **kwargs):
            with Popen(*popenargs, **kwargs) as p:
                try:
                    return p.wait(timeout=timeout)
                except KeyboardInterrupt:
                    p.terminate()
                    p.wait()
                    time.sleep(10.)
                    raise
                except:
                    p.terminate()
                    p.wait()
                    raise

        experiments = [p for p in glob.glob(os.path.join(self.root, pattern)) if p in self.experiments]
        for p in experiments:
            P = self.load_params(p)
            if P['_status'] == 'registered':
                args = list(flags)
                if 'sbatch' in options and '--job-name' not in options:
                    args += [
                        f'--job-name={P["_name"]}', f'--output={os.path.join(P["_root"], P["_name"], "slurm.out")}']
                subprocess_args = args + [os.path.join(p, 'run.sh')]
                print('\nRunning: {}'.format(" ".join(subprocess_args)))
                call(subprocess_args)

    def unlink(self, pattern='*'):
        """Unlink all experiments matching pattern. Does not delete experiment folders simply deletes the experiment
        paths from the experiment folder. To delete call method ``clean``."""
        self.check_initialised()
        remove_paths = [p for p in glob.glob(os.path.join(self.root, pattern)) if p in self.experiments]
        if len(remove_paths) != 0:
            print("Removing Experiments...")
            for p in remove_paths:
                print(p)
                self.experiments.remove(p)
            self._to_yml()
            print("Note models are removed from the experiment list only. To remove the model directories run"
                  "experiment clean")
        else:
            print(f"No experiments match pattern {pattern}")

    def relink(self, pattern='*'):
        """Re-link all experiment folders that match ``pattern`` (and are not currently managed by the experiment
        manager)"""
        self.check_initialised()
        subdirs = [x[0] for x in os.walk(self.root)
                   if x[0] != self.root
                   and x[0] in glob.glob(os.path.join(self.root, pattern))
                   and x[0] not in self.experiments]
        if len(subdirs) == 0:
            print("No experiements to link that match pattern and aren't managed already")

        for d in subdirs:
            params, defaults = self.load_params(d, True), self.load_defaults()
            if any([k not in defaults and not k.startswith('_') for k in params]):
                print(f'Cannot re-link folder {d} as params are not compatible with defaults')
            else:
                print(f'Relinking {d}')
                self.experiments += [d]
                self.overides += [{pk: pv for pk, pv in params.items() if not pk.startswith('_') and defaults[pk] != pv}]
        self._to_yml()


