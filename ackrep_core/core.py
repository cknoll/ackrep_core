import secrets
import yaml
import os
import time
import subprocess
from jinja2 import Environment, FileSystemLoader
from ipydex import Container  # for functionality

# noinspection PyUnresolvedReferences
from ipydex import IPS  # for debugging only

# settings might be accessd from other modules which import this one (core)
# noinspection PyUnresolvedReferences
from django.conf import settings

from . import models

mod_path = os.path.dirname(os.path.abspath(__file__))


class ResultContainer(Container):
    pass


valid_types = [
    "problem_class",
    "problem_specification",
    "problem_solution",
    "method",
    "doc",
    "dataset",
    "comment",
    ]


required_generic_meta_data = {
    "pk": "=5",
    "type": valid_types,
    "name": ">3, <100",
    "short_description": "<500",
    "version": ">5, <10",
    "tags": None,
    "creator": ">3, <100",
    "editors": None,
    "creation_date": None,
    "related_docs": None,
    "related_datasets": None,
    "external_references": None,
    "notes": None,
    }


def gen_random_key():
    return "".join([c for c in secrets.token_urlsafe(10).upper() if c.isalnum()])[:5]


def get_metadata_from_file(path, check_sanity=False):
    """
    Load metadata
    :param path:
    :param check_sanity:       flag whether to check the sanity of the metadata against the models
    :return:
    """
    with open(path) as f:
        data = yaml.load(f, Loader=yaml.FullLoader)

    # TODO: this check is outdated -> temporarily deactivated
    if check_sanity and not set(required_generic_meta_data.keys()).issubset(data.keys()):
        msg = f"In the provided file `{path}` at least one required key is missing."
        raise KeyError(msg)

    # TODO: add more consistency checks

    return data


def convert_dict_to_yaml(data, target_path=None):

    class MyDumper(yaml.Dumper):
        """
        This class results in the preferred indentation style
        source: https://stackoverflow.com/a/39681672/333403
        """

        def increase_indent(self, flow=False, indentless=False):
            return super(MyDumper, self).increase_indent(flow, False)

    yml_txt = yaml.dump(data, Dumper=MyDumper, default_flow_style=False, sort_keys=False, indent=4)

    if target_path is not None:
        with open(target_path, "w") as f:
            f.write(yml_txt)

    return yml_txt


def get_entity(key, hint=None):
    # TODO: remove argument `hint`

    assert hint is None, "the path-hint in the caller must be removed now"

    results = []
    for entity_type in models.all_entities:
        res = entity_type.objects.filter(key=key)
        results.extend(res)

    if len(results) == 0:
        msg = f"No entity with key '{key}' could be found. Make sure that the database is in sync with repo."
        # TODO: this should be a 404 Error in the future
        raise ValueError(msg)
    elif len(results) > 1:
        msg = f"There have been multiple entities with key '{key}'. "
        raise ValueError(msg)

    entity = results[0]

    return entity


def render_template(tmpl_path, context, target_path=None, base_path=None, special_str="template_"):
    """
    Render a jinja2 template and save it to target_path. If target_path ist `None` (default),
    autogenerate it by dropping the then mandatory `template_` substring of the templates filename
    (or another nonempty special string).

    :param tmpl_path:   template path (relative to the modules path, usually starts with "templates/")
    :param context:     dict with context data for rendering
    :param target_path: None or string
    :param base_path:   None or string (if None then the absolute path of this module will be used)
    :param target_path: None or string
    :param special_str: default: "template_"; will be replaced by '' if target_path is given
    :return:
    """

    path, fname = os.path.split(tmpl_path)
    assert path != ""

    if base_path is None:
        base_path = mod_path

    path = os.path.join(base_path, path)

    jin_env = Environment(loader=FileSystemLoader(path))

    if target_path is None:
        assert 1 < len(special_str) < len(fname) and (fname.count(special_str) == 1)
        res_fname = fname.replace(special_str, "")
        target_path = os.path.join(path, res_fname)

    template = jin_env.get_template(fname)
    if "warning" not in context:
        time_string = time.strftime("%Y-%m-%d %H:%M:%S")
        context["warning"] = f"This file was autogenerated from the template: {fname} ({time_string})."
    result = template.render(context=context)

    with open(target_path, "w") as resfile:
        resfile.write(result)

    # also return the result (useful for testing)
    return target_path


def get_files_by_pattern(directory, match_func):
    """
    source:  https://stackoverflow.com/questions/8505457/how-to-crawl-folders-to-index-files
    :param directory: 
    :param match_func:      example: `lambda fn: fn == "metadata.yml"`
    :return: 
    """
    for path, dirs, files in os.walk(directory):
        # TODO: this should be made more robust
        if "_template" in path:
            continue
        for f in filter(match_func, files):
            yield os.path.join(path, f)


def clear_db():

    for e in models.all_entities:
        e.objects.all().delete()


def load_repo_to_db(startdir):

    clear_db()

    meta_data_files = get_files_by_pattern(startdir, lambda fn: fn == "metadata.yml")
    entity_list = []

    for md_path in meta_data_files:
        print(md_path)

        md = get_metadata_from_file(md_path)
        e = models.create_entity_from_metadata(md)
        e.base_path = os.path.abspath(os.path.split(md_path)[0])

        # store to db
        e.save()
        entity_list.append(e)


def get_entity_dict_from_db():
    """
    get all entities which are currently in the database
    :return:
    """
    entity_type_list = models.get_entities()

    entity_dict = {}

    for et in entity_type_list:
        object_list = list(et.objects.all())

        entity_dict[et.__name__] = object_list

    return entity_dict


def clone_git_repo(giturl):
    res = subprocess.run(["git", "clone", giturl], capture_output=True)
    res.exited = res.returncode
    res.stdout = res.stdout.decode("utf8")
    res.stderr = res.stderr.decode("utf8")
