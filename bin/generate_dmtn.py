import glob
import os.path
import subprocess
import textwrap

from abc import ABC, abstractmethod
from datetime import datetime
from io import StringIO
from contextlib import contextmanager

from milestones import (
    add_rst_citations,
    get_latest_pmcs_path,
    get_local_data_path,
    load_milestones,
    write_output,
)


HEADING_CHARS = '#=-^"'

WBS_DEFINITIONS = {
    "06C.00": "SITCOM Management Level 2 Milestones",
    "06C.01": "Systems Engineering",
    "06C.02": "Commissioning",
}


def underline(text, character, overline=False):
    line = character * len(text) + "\n"
    return f"{line if overline else ''}{text}\n{line}".strip()


def add_context(context_name, context_manager, *, needs_level=False):
    def wrapper(cls):
        @contextmanager
        def new_method(self, *args, **kwargs):
            if needs_level:
                level = self._level + 1 if hasattr(self, "_level") else 1
                manager = context_manager(level, *args, **kwargs)
            else:
                manager = context_manager(*args, **kwargs)
            yield manager
            self._buffer.write(manager.get_result())

        setattr(cls, context_name, new_method)
        return cls

    return wrapper


class TextAccumulator(ABC):
    def __init__(self):
        self._buffer = StringIO()

    @abstractmethod
    def get_result(self):
        return self._buffer.getvalue()


class Paragraph(TextAccumulator):
    def write_line(self, line):
        self._buffer.write(line + "\n")

    def get_result(self):
        return super().get_result() + "\n"


@add_context("paragraph", Paragraph)
class Directive(TextAccumulator):
    def __init__(self, name, argument=None, options={}):
        super().__init__()
        self._buffer.write(f"{name}:: {argument if argument else ''}\n")
        for name, value in options.items():
            if value:
                self._buffer.write(f":{name}: {value}\n")
            else:
                self._buffer.write(f":{name}:\n")
        self._buffer.write("\n")

    def get_result(self):
        return ".." + textwrap.indent(self._buffer.getvalue(), "   ")[2:] + "\n"


class Admonition(Directive):
    pass


class Figure(Directive):
    def __init__(self, filename, target=None):
        opts = {"target": target} if target else {}
        super().__init__("figure", filename, opts)


@add_context("paragraph", Paragraph)
class BulletListItem(TextAccumulator):
    def get_result(self):
        line_start = "-"
        indented_result = textwrap.indent(
            self._buffer.getvalue(), " " * (len(line_start) + 1)
        )
        return line_start + indented_result[len(line_start):]


@add_context("bullet", BulletListItem)
class BulletList(TextAccumulator):
    def get_result(self):
        return super().get_result()


# Can't reference BulletList before it is defined
BulletListItem = add_context("bullet_list", BulletList)(BulletListItem)


@add_context("paragraph", Paragraph)
@add_context("admonition", Admonition)
@add_context("figure", Figure)
@add_context("bullet_list", BulletList)
@add_context("directive", Directive)
class Section(TextAccumulator):
    def __init__(self, level, title, anchor=None):
        super().__init__()
        self._level = level
        if anchor:
            self._buffer.write(f".. _{anchor}:\n\n")
        self._buffer.write(underline(title, HEADING_CHARS[self._level]) + "\n\n")

    def get_result(self):
        return super().get_result()


# Can't reference Section before it is defined.
Section = add_context("section", Section, needs_level=True)(Section)


@add_context("paragraph", Paragraph)
@add_context("section", Section, needs_level=True)
@add_context("admonition", Admonition)
@add_context("figure", Figure)
@add_context("bullet_list", BulletList)
@add_context("directive", Directive)
class ReSTDocument(TextAccumulator):
    def __init__(self, title=None, subtitle=None, options=None):
        super().__init__()
        if title:
            self._buffer.write(underline(title, HEADING_CHARS[0], True) + "\n")
        if subtitle:
            self._buffer.write(underline(subtitle, HEADING_CHARS[1], True) + "\n")

        options = options or {}
        for name, value in options.items():
            self._buffer.write(f":{name}:")
            if value:
                self._buffer.write(f" {value}")
            self._buffer.write("\n")

        if title or subtitle or options:
            self._buffer.write("\n")

    def get_result(self):
        return super().get_result()


def get_version_info():
    pmcs_path = get_latest_pmcs_path()
    git_dir = os.path.dirname(pmcs_path)
    sha, date = (
        subprocess.check_output(
            ["git", "log", "-1", "--pretty=format:'%H %ad'", "--date=unix"], cwd=git_dir
        )
        .decode("utf-8")
        .strip("'")
        .split()
    )
    p6_date = datetime.strptime(os.path.basename(pmcs_path), "%Y%m-ME.xls")

    return sha, datetime.utcfromtimestamp(int(date)), p6_date


def get_extreme_dates(milestones):
    earliest_ms, latest_ms = None, None
    for ms in milestones:
        if not earliest_ms or ms.due < earliest_ms:
            earliest_ms = ms.due
        if not latest_ms or ms.due > latest_ms:
            latest_ms = ms.due
    return earliest_ms, latest_ms


def generate_dmtn(milestones, wbs):
    doc = ReSTDocument(options={"tocdepth": 1})

    wbs_list = set(ms.wbs[:6] for ms in milestones if ms.wbs.startswith(wbs))

    with doc.section("Provenance") as my_section:
        with my_section.paragraph() as p:
            sha, timestamp, p6_date = get_version_info()
            p.write_line(
                f"This document was generated based on the contents of "
                f"the `lsst-dm/milestones <https://github.com/lsst-dm/milestones>`_ "
                f"repository, version "
                f"`{sha[:8]} <https://github.com/lsst-dm/milestones/commit/{sha}>`_, "
                f"dated {timestamp.strftime('%Y-%m-%d')}."
            )
            p.write_line(
                f"This corresponds to the status recorded in the project "
                f"controls system for {p6_date.strftime('%B %Y')}."
            )
            p.write_line(
                f"`Download the report.csv here. <./report.csv>`_"
            )

    with doc.section("Summary") as my_section:
        with my_section.figure("_static/blockschedule.png") as f:
            with f.paragraph() as p:
                p.write_line("Current block schedule. `Download the PDF of this Block Schedule here."
                             " <./blockschedule.pdf>`_")
        with my_section.paragraph() as p:
            dm_milestones = [ms for ms in milestones if ms.wbs.startswith(wbs)]
            levels = [ms.level for ms in dm_milestones]
            p.write_line(
                f"The SITCOM Subsystem is currently tracking "
                f"{len(dm_milestones)} milestones: "
                f"{levels.count(1)} at Level 1, "
                f"{levels.count(2)} at Level 2, "
                f"{levels.count(3)} at Level 3, "
                f"and {levels.count(4)} at Level 4."
            )
            if levels.count(None) != 0:
                p.write_line(f"{levels.count(None)} have no level defined.")
            p.write_line(
                f"Of these, {len([ms for ms in dm_milestones if ms.completed])} "
                f"have been completed."
            )
            p.write_line(
                f"Of the incomplete milestones, "
                f"{sum(1 for ms in dm_milestones if ms.due < datetime.now() and not ms.completed)} "
                f"are late relative to the baseline schedule, while "
                f"the remainder are scheduled for the future."
            )
        for bd in ["", "SIT", "COM", "SUM"]:
            with my_section.figure(f"_static/burndown{bd}.png") as f:
                with f.paragraph() as p:
                    p.write_line(f"{bd} Milestone completion as a function of date.")

    with doc.section("Currently overdue milestones") as my_section:
        overdue_milestones = [
            ms
            for ms in milestones
            if ms.due < datetime.now() and ms.wbs.startswith(wbs) and not ms.completed
        ]

        if overdue_milestones:
            for msprefix in ["SIT", "COM", "SUM"]:
                with my_section.paragraph() as p:
                    p.write_line(f"Overdue {msprefix} milestones")
                with my_section.bullet_list() as my_list:
                    for ms in sorted(overdue_milestones, key=lambda ms: ms.wbs + ms.code):
                        if ms.code.startswith(msprefix):
                            with my_list.bullet() as b:
                                with b.paragraph() as p:
                                    p.write_line(
                                        f"`{ms.code}`_: {ms.name} "
                                        f"[Due {ms.due.strftime('%Y-%m-%d')}]"
                                    )
        else:
            with my_section.paragraph() as p:
                p.write_line("None.")

    with doc.section("Milestones by due date") as my_section:
        earliest_ms, latest_ms = get_extreme_dates(
            ms for ms in milestones if ms.wbs.startswith(wbs)
        )
        first_month = datetime(earliest_ms.year, earliest_ms.month, 1)
        last_month = (
            datetime(latest_ms.year, latest_ms.month + 1, 1)
            if latest_ms.month < 12
            else datetime(latest_ms.year + 1, 1, 1)
        )

        for year in range(latest_ms.year, earliest_ms.year - 1, -1):
            for month in range(12, 0, -1):
                start_date = datetime(year, month, 1)
                end_date = (
                    datetime(year, month + 1, 1)
                    if month < 12
                    else datetime(year + 1, 1, 1)
                )
                if end_date <= first_month or start_date >= last_month:
                    continue
                with my_section.section(f"Due in {start_date.strftime('%B %Y')}") as s:
                    output = [
                        ms
                        for ms in milestones
                        if ms.due >= start_date
                        and ms.due < end_date
                        and ms.wbs.startswith(wbs)
                    ]
                    with s.bullet_list() as my_list:
                        if output:
                            for ms in output:
                                with my_list.bullet() as b:
                                    with b.paragraph() as p:
                                        p.write_line(f"`{ms.code}`_: {ms.name}")
                        else:
                            with my_list.bullet() as b:
                                with b.paragraph() as p:
                                    p.write_line("No milestones due.")

    with doc.section("Milestones by WBS") as my_section:
        for wbs in sorted(wbs_list):
            with my_section.section(f"{wbs}: {WBS_DEFINITIONS[wbs]}") as section:
                with section.figure(
                    f"_static/graph_{wbs}.png", target=f"_static/graph_{wbs}.png"
                ) as f:
                    with f.paragraph() as p:
                        p.write_line(
                            f"Relationships between milestones in WBS {wbs} and "
                            f"their immediate predecessors and successors. "
                            f"Ellipses correspond to milestones within this WBS "
                            f"element; rectangles to those in other elements. "
                            f"Blue milestones have been completed; orange "
                            f"milestones are overdue."
                        )
                for ms in sorted(milestones, key=lambda ms: ms.due):
                    if not ms.wbs.startswith(wbs):
                        continue
                    with section.section(
                        f"{ms.code}: {ms.name}", ms.code
                    ) as subsection:
                        with subsection.bullet_list() as my_list:
                            with my_list.bullet() as my_bullet:
                                with my_bullet.paragraph() as p:
                                    level = ms.level if ms.level else "Undefined"
                                    p.write_line(f"**Level:** {level}")
                            if ms.test_spec or ms.jira_testplan:
                                with my_list.bullet() as my_bullet:
                                    with my_bullet.paragraph() as p:
                                        p.write_line("**Test specification:**")
                                        if ms.test_spec:
                                            p.write_line(add_rst_citations(f"{ms.test_spec}"))
                                        else:
                                            p.write_line("Undefined")
                                        if ms.jira_testplan:
                                            p.write_line(f":jirab:`{ms.jira_testplan}`")
                            with my_list.bullet() as my_bullet:
                                with my_bullet.paragraph() as p:
                                    p.write_line(
                                        f"**Due:** {ms.due.strftime('%Y-%m-%d')}"
                                    )
                            with my_list.bullet() as my_bullet:
                                with my_bullet.paragraph() as p:
                                    if ms.completed:
                                        p.write_line(
                                            f"**Completed:** {ms.completed.strftime('%Y-%m-%d')}"
                                        )
                                    else:
                                        p.write_line("**Completion pending**")
                                    if ms.jira:
                                        p.write_line(f":jirab:`{ms.jira}`")
                        if ms.description:
                            with subsection.paragraph() as p:
                                for line in ms.description.strip().split(". "):
                                    p.write_line(add_rst_citations(line.strip(" .") + "."))
                        else:
                            with subsection.admonition(
                                "warning", "No description available"
                            ):
                                pass

    with doc.section("Bibliography") as bib:
        with bib.directive(
            "bibliography", " ".join(glob.glob("lsstbib/*.bib")), {"style": "lsst_aa"},
        ):
            pass

    return doc.get_result()


if __name__ == "__main__":
    milestones = load_milestones(get_latest_pmcs_path(), get_local_data_path())
    write_output("index.rst", generate_dmtn(milestones, "06C"), comment_prefix="..")
