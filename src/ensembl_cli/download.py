from __future__ import annotations

import os

import click

from cogent3 import open_

from ensembl_cli.ftp_download import download_data, listdir
from ensembl_cli.name import EnsemblDbName
from ensembl_cli.species import Species
from ensembl_cli.util import ENSEMBLDBRC, makedirs, read_config


def get_download_checkpoint_path(local_path, dbname):
    """returns path to db checkpoint file"""
    return os.path.join(local_path, dbname, "ENSEMBLDB_DOWNLOADED")


def is_downloaded(local_path, dbname):
    """returns True if checkpoint file exists for dbname"""
    chk = get_download_checkpoint_path(local_path, dbname)
    return os.path.exists(chk)


_cfg = os.path.join(ENSEMBLDBRC, "ensembldb_download.cfg")




def valid_seq_file(name: str) -> bool:
    """unmasked genomic DNA sequences"""
    return _valid_seq.search(name) is not None


def download_dbs(configpath, verbose, debug):
    if configpath.name == _cfg:
        click.secho("WARN: using the built in demo cfg, will write to /tmp", fg="red")

    host, remote_path, release, local_path, species_dbs = read_config(
        configpath, verbose=verbose
    )

    # TODO identify single file name convention enabling single file downloads from subdir
    remote_template = f"{remote_path}/release-{release}/" + "{}/{}"

    if verbose:
        click.secho(f"DOWNLOADING\n  ensembl release={release}", fg="green")
        click.secho("\n".join(f"  {d.name}" for d in db_names), fg="green")
        click.secho(f"\nWRITING to output path={local_path}\n", fg="green")

    for key in species_dbs:
        db_prefix = Species.get_ensembl_db_prefix(key)
        local_root = local_path / db_prefix
        local_root.mkdir(parents=True, exist_ok=True)
        with open_(local_root / "DOWNLOADED_CHECKSUMS", mode="w") as chkpt:
            for subdir in ("fasta", "gff3"):
                path = remote_template.format(subdir, db_prefix)
                if subdir == "fasta":
                    path += "/dna"
                dest_path = local_path / db_prefix / subdir
                dest_path.mkdir(parents=True, exist_ok=True)
                paths = [f"{path}/{fn}" for fn in listdir(host, path=path, debug=debug)]
                download_data(
                    host,
                    dest_path,
                    paths,
                    description=f"{db_prefix[:5]}.../{subdir}",
                    checkpoint_file=chkpt,
                )

    # now check if downloaded files match expected checksum

    click.secho(f"\nWROTE to output path={local_path}\n", fg="green")
