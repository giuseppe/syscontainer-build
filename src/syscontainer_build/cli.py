#!/usr/bin/env python
# Copyright (C) 2017 Red Hat
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
System Container build tool.
"""

import json
import os
import shutil
import subprocess
import tempfile

import click
import jinja2


MANIFEST_JSON_STRUCT = {
    "version": "1.0",
    "defaultValues": {},
}

SERVICE_TEMPLATE = """\
[Unit]
Description={}

[Service]
ExecStart=$EXEC_START
ExecStop=$EXEC_STOP
Restart=on-failure
WorkingDirectory=$DESTDIR

[Install]
WantedBy=multi-user.target"""


def _expand_path(path):
    return os.path.realpath(os.path.expanduser(path))


def _mkdir(path):
    """
    Shortcut for making directories.
    """
    path = _expand_path(path)
    try:
        os.mkdir(path)
    except FileExistsError:
        pass

    return path


def _pushd(dir):
    original_cwd = os.getcwd()
    os.chdir(dir)
    return lambda: os.chdir(original_cwd)


@click.command('generate-files')
@click.option('--output', '-o', prompt='Directory to write in', default='.')
@click.option('--description', '-d', prompt='Description of container')
@click.option('--default', '-D', multiple=True,
              help='Default values in the form of key=value')
def generate_files(output, description, default):
    """
    Generates manifest.json, config.template, and service.template
    for a system container.
    """
    output = _mkdir(output)
    manifest_struct = MANIFEST_JSON_STRUCT.copy()
    for item in default:
        try:
            k, v = item.split('=')
            manifest_struct['defaultValues'][k] = v
        except ValueError as error:
            click.echo('{} not in a=b format. Skipping...'.format(item))

    manifest_out = os.path.sep.join([output, 'manifest.json'])
    with open(manifest_out, 'w') as manifest:
        json.dump(manifest_struct, manifest, indent='    ')

    service_out = os.path.sep.join([output, 'service.template'])
    with open(service_out, 'w') as service:
        loader = jinja2.PackageLoader('syscontainer_build')
        rendered = loader.load(
            jinja2.Environment(), 'service.template.j2').render(
                description=description)
        service.write(rendered)

    temp_dir = tempfile.mkdtemp()
    _popd = _pushd(temp_dir)
    try:
        subprocess.check_call(['ocitools', 'generate'])
        config_out = os.path.sep.join([output, 'config.json.template'])
        shutil.move('config.json', config_out)
    except subprocess.CalledProcessError as error:
        raise click.exceptions.ClickException(
            'ocitools generate failed: {}'.format(error))
    finally:
        _popd()
        shutil.rmtree(temp_dir)


@click.command('generate-dockerfile')
@click.argument('name', required=True)
@click.option('--from-base', '-f', default='centos:latest')
@click.option('--maintainer', '-m', default='{}@{}'.format(
    os.getenv('USER', 'UNKNOWN'), os.getenv('HOSTNAME', 'UNKNOWN')))
@click.option('--license', '-l', default='UNKNOWN')
@click.option('--summary', '-s', prompt='Summary')
@click.option('--version', '-v', default='1')
@click.option('--help-text', '-H', prompt='Help')
@click.option('--architecture', '-a', default='x86_64')
@click.option('--scope', '-S', default='public', type=click.Choice([
    'private', 'authoritative-source-only', 'restricted', 'public']))
@click.option('--output', '-o', default='.')
def generate_dockerfile(
        name, from_base, maintainer, license, summary, version,
        help_text, architecture, scope, output):
    """
    Generates a Dockerfile for use when creating a system container.
    """
    output = _mkdir(output)
    with open(os.path.sep.join([output, 'Dockerfile']), 'w') as dockerfile:
        loader = jinja2.PackageLoader('syscontainer_build')
        rendered = loader.load(jinja2.Environment(), 'Dockerfile.j2').render(
            from_base=from_base, name=name, maintainer=maintainer,
            license=license, summary=summary, version=version,
            help_text=help_text, architecture=architecture, scope=scope)
        dockerfile.write(rendered)


@click.command('build')
@click.option('--path', '-p', default='.')
@click.argument('tag', required=True)
def build(path, tag):
    _popd = _pushd(path)
    try:
        subprocess.check_call(['docker', 'build', '-t', tag, '.'])
    except subprocess.CalledProcessError as error:
        raise click.exceptions.ClickException(
            'Can not build image: {}'.format(error))
    finally:
        _popd()


@click.command('tar')
@click.argument('image', required=True)
def docker_image_to_tar(image):
    try:
        subprocess.check_call([
            'docker', 'save', '-o', '{}.tar'.format(image), image])
    except subprocess.CalledProcessError as error:
        raise click.exceptions.ClickException(
            'Unable to export image to a tar: {}'.format(error))


def main():
    """
    Main entry point.
    """
    cli = click.Group()
    cli.add_command(generate_files)
    cli.add_command(generate_dockerfile)
    cli.add_command(build)
    cli.add_command(docker_image_to_tar)
    cli()


if __name__ == '__main__':
    main()