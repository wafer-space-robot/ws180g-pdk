# SPDX-License-Identifier: Apache-2.0
"""Naming checker: library, cell, corner and device names, and the tree walk."""

import subprocess
from decimal import Decimal

import pytest
from ws180g_build.naming import (
    NamingError,
    check_tree,
    parse_cell,
    parse_corner,
    parse_device,
    parse_library,
)


@pytest.mark.parametrize(
    "name",
    ["ws180g005_fd_pr", "ws180g005_fd_sc_gp9t5v0", "ws180g005_fd_io", "ws180g035_fd_sc_ls"],
)
def test_valid_library(name):
    assert parse_library(name).process == name.split("_")[0]


def test_library_fields():
    lib = parse_library("ws180g005_fd_sc_gp9t5v0")
    assert (lib.process, lib.source, lib.type, lib.name) == ("ws180g005", "fd", "sc", "gp9t5v0")
    assert parse_library("ws180g005_fd_pr").name is None


@pytest.mark.parametrize(
    "name", ["ws180g005_fd_sc_gp_9t", "abc123_osu_sc_7t", "ws180g005_fd_sc_7t"]
)
def test_invalid_library(name):
    with pytest.raises(NamingError, match=name):
        parse_library(name)


def test_cell():
    cell = parse_cell("ws180g005_fd_sc_gp9t5v0__nand2_1")
    assert (cell.library, cell.cell, cell.size) == ("ws180g005_fd_sc_gp9t5v0", "nand2", "1")
    assert parse_cell("ws180g005_fd_pr__nmos").size is None
    with pytest.raises(NamingError):
        parse_cell("ws180g005_fd_sc_7t__nand2")
    with pytest.raises(NamingError):
        parse_cell("nand2_1")


@pytest.mark.parametrize(
    ("name", "temp", "volt", "flags"),
    [
        ("tt_025C_5v00", 25, Decimal("5.00"), []),
        ("ss_125C_4v50", 125, Decimal("4.50"), []),
        ("ff_n40C_5v50", -40, Decimal("5.50"), []),
        ("tt_025C_5v00_stat", 25, Decimal("5.00"), ["stat"]),
    ],
)
def test_valid_corner(name, temp, volt, flags):
    corner = parse_corner(name)
    assert (corner.temp_c, corner.voltage, corner.flags) == (temp, volt, flags)


def test_invalid_corner():
    with pytest.raises(NamingError):
        parse_corner("typ_1p20V_25C")


@pytest.mark.parametrize(
    "name",
    ["nfet_05v0", "diode_pw2nd_05v0", "res_generic_po", "res_high_po", "cap_mim_m4",
     "npn_05v0", "nfet_05v0_dnw", "esd_rf_nfet_05v0"],
)
def test_valid_device(name):
    parse_device(name)


def test_device_fields():
    dev = parse_device("nfet_05v0_dnw")
    assert (dev.kind, dev.voltage, dev.properties) == ("nfet", Decimal("5.0"), ["dnw"])
    assert parse_device("esd_rf_nfet_05v0").prefixes == ["esd", "rf"]
    assert parse_device("diode_pw2nd_05v0").kind == "diode_pw2nd"
    assert parse_device("res_generic_po").voltage is None


def test_invalid_device():
    with pytest.raises(NamingError, match="nfet5v"):
        parse_device("nfet5v")


def test_error_message():
    with pytest.raises(NamingError) as info:
        parse_corner("bogus")
    assert str(info.value).startswith("bogus: ")


def test_process_names_come_from_process_data(process):
    for variant in process.variants:
        parse_library(f"{variant}_fd_pr")


def test_check_tree(tmp):
    lib = tmp / "libraries" / "ws180g005_fd_sc_gp9t5v0"
    (lib / "cells" / "ws180g005_fd_sc_gp9t5v0__nand2_1").mkdir(parents=True)
    (lib / "cells" / "ws180g005_fd_sc_gp9t5v0__nand2_1" / "ws180g005_fd_sc_gp9t5v0__nand2_1__tt_025C_5v00.lib").touch()
    (lib / "README.md").touch()
    (tmp / "libraries" / ".gitkeep").touch()
    assert check_tree(tmp) == []

    (tmp / "libraries" / "ws180g005_fd_sc_gp_9t").mkdir()
    errors = check_tree(tmp)
    assert len(errors) == 1
    assert "ws180g005_fd_sc_gp_9t" in errors[0]


def test_check_tree_bad_corner_file_and_release_tree(tmp):
    cell = tmp / "libraries" / "ws180g005_fd_pr" / "cells" / "ws180g005_fd_pr__nmos"
    cell.mkdir(parents=True)
    (cell / "ws180g005_fd_pr__nmos__typ_1p20V_25C.lib").touch()
    (cell / "ws180g005_fd_pr__nmos__tt_025C_5v00.lib").touch()
    errors = check_tree(tmp)
    assert len(errors) == 1
    assert "typ_1p20V_25C" in errors[0]

    ref = tmp / "libs.ref" / "ws180g005_fd_pr" / "lef"
    ref.mkdir(parents=True)
    (ref / "nmos.lef").touch()
    (ref / "Bad_Cell.lef").touch()
    assert len(check_tree(tmp)) == 2


def test_check_tree_missing_directories(tmp):
    assert check_tree(tmp) == []


def test_repository_tree_is_clean(repo_root):
    assert check_tree(repo_root) == []


def test_check_tree_wrong_library_and_cell_in_corner_file(tmp):
    cell = tmp / "libraries" / "ws180g005_fd_pr" / "cells" / "ws180g005_fd_pr__nmos"
    cell.mkdir(parents=True)
    (cell / "wrongprefix__nmos__tt_025C_5v00.lib").touch()
    (cell / "ws180g005_fd_io__nmos__tt_025C_5v00.lib").touch()
    (cell / "ws180g005_fd_pr__Bad-Cell__tt_025C_5v00.lib").touch()
    (cell / "ws180g005_fd_pr__nmos__tt_025C_5v00.lib").touch()
    errors = check_tree(tmp)
    assert len(errors) == 3
    assert any("wrongprefix" in e for e in errors)
    assert any("ws180g005_fd_io__nmos" in e for e in errors)
    assert any("Bad-Cell" in e for e in errors)


def test_check_tree_unprefixed_cell_one_error_and_dot_dirs(tmp):
    cells = tmp / "libraries" / "ws180g005_fd_pr" / "cells"
    (cells / "nmos").mkdir(parents=True)
    (cells / ".git").mkdir()
    assert len(check_tree(tmp)) == 1


def test_console_script_exit_codes(tmp, repo_root):
    def run(root):
        return subprocess.run(
            ["uv", "run", "ws180g-check-names", str(root)],
            check=False, capture_output=True, text=True, cwd=repo_root,
        )

    assert run(repo_root).returncode == 0
    (tmp / "libraries" / "ws180g005_fd_sc_gp_9t").mkdir(parents=True)
    result = run(tmp)
    assert result.returncode == 1
    assert "ws180g005_fd_sc_gp_9t" in result.stdout
