"""
Walks a Stepik course's hierarchy (course -> section (module) -> unit -> lesson -> step)
via the API and returns one ordered tree, with filesystem-safe
directory names already assigned at every level.

Step nodes don't carry a "title" key from here -- export_course.main() sets
step["title"] on each node after render_step() renders it, and toc_builder's
build_toc() relies on that having run first (it falls back to dir_name
otherwise).
"""

import logging

from slugify import slugify

logger = logging.getLogger("stepik_export")

MAX_SLUG_LEN = 50
DIR_INDEX_WIDTH = 3


def _slug(title):
    return slugify(title or "untitled", max_length=MAX_SLUG_LEN)


def _dir_name(index, title, prefix=""):
    return f"{prefix}{index:0{DIR_INDEX_WIDTH}d}_{_slug(title)}"


def _build_lesson_node(lesson, index, step_id_to_step):
    lesson_steps = []
    for step_id in lesson.get("steps", []):
        step = step_id_to_step.get(step_id)
        if step is None:
            logger.warning("lesson %s references step %s which could not be resolved, skipping", lesson["id"], step_id)
            continue
        lesson_steps.append(step)
    lesson_steps.sort(key=lambda step: step.get("position", 0))

    steps = []
    for step_index, step in enumerate(lesson_steps, start=1):
        block = step.get("block", {})
        steps.append(
            {
                "id": step["id"],
                "dir_name": _dir_name(step_index, block.get("name", "unknown"), prefix="step_"),
                "block": block,
                "raw": step,
            }
        )

    title = lesson.get("title", "")
    return {
        "id": lesson["id"],
        "title": title,
        "dir_name": _dir_name(index, title, prefix="lesson_"),
        "steps": steps,
    }


def _build_module_node(section, index, unit_id_to_unit, lesson_id_to_lesson, step_id_to_step):
    module_units = []
    for unit_id in section.get("units", []):
        unit = unit_id_to_unit.get(unit_id)
        if unit is None:
            logger.warning(
                "module %s references unit %s which could not be resolved, skipping",
                section["id"],
                unit_id,
            )
            continue
        module_units.append(unit)
    module_units.sort(key=lambda unit: unit.get("position", 0))

    lessons = []
    for lesson_index, unit in enumerate(module_units, start=1):
        lesson = lesson_id_to_lesson.get(unit["lesson"])
        if lesson is None:
            logger.warning(
                "unit %s (module %s) references lesson %s which could not be resolved, skipping",
                unit["id"],
                section["id"],
                unit["lesson"],
            )
            continue
        lessons.append(_build_lesson_node(lesson, lesson_index, step_id_to_step))

    title = section.get("title", "")
    return {
        "id": section["id"],
        "title": title,
        "dir_name": _dir_name(index, title, prefix="module_"),
        "lessons": lessons,
    }


def build_course_tree(client, course_id):
    courses = client.get_by_ids("courses", [course_id])
    if not courses:
        raise ValueError(f"Course {course_id} not found or not accessible with current auth scope")
    course = courses[0]

    sections = client.get_by_ids("sections", course.get("sections", []))
    sections.sort(key=lambda section: section.get("position", 0))

    all_unit_ids = [unit_id for section in sections for unit_id in section.get("units", [])]
    units = client.get_by_ids("units", all_unit_ids)
    unit_id_to_unit = {unit["id"]: unit for unit in units}

    lessons = client.get_by_ids("lessons", [unit["lesson"] for unit in units])
    lesson_id_to_lesson = {lesson["id"]: lesson for lesson in lessons}

    all_step_ids = [step_id for lesson in lessons for step_id in lesson.get("steps", [])]
    steps = client.get_by_ids("steps", all_step_ids)
    step_id_to_step = {step["id"]: step for step in steps}

    title = course.get("title", "")
    return {
        "id": course["id"],
        "title": title,
        "dir_name": f"{course['id']}_{_slug(title)}",
        "modules": [
            _build_module_node(section, index, unit_id_to_unit, lesson_id_to_lesson, step_id_to_step)
            for index, section in enumerate(sections, start=1)
        ],
    }
