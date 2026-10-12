"""
Walks a Stepik course's hierarchy (course -> section (module) -> unit -> lesson -> step)
via the API and returns one ordered tree, with filesystem-safe
directory names already assigned at every level.
"""

import logging

from slugify import slugify

logger = logging.getLogger("stepik_export")

MAX_SLUG_LEN = 50
DIR_INDEX_WIDTH = 3


class CourseNotFoundError(Exception):
    pass


def _slug(title):
    return slugify(title or "", max_length=MAX_SLUG_LEN) or "untitled"


def _dir_name(prefix, position, title):
    return f"{prefix}{position:0{DIR_INDEX_WIDTH}d}_{_slug(title)}"


def _resolve_ids_to_items(owner_label, kind, ids, id_to_item):
    items = []
    for item_id in ids:
        item = id_to_item.get(item_id)
        if item is None:
            logger.warning("%s references %s %s which could not be resolved, skipping", owner_label, kind, item_id)
            continue
        items.append(item)
    return sorted(items, key=lambda item: item["position"])


def _build_lesson_node(lesson, position, step_id_to_step):
    lesson_steps = _resolve_ids_to_items(f"lesson {lesson['id']}", "step", lesson.get("steps", []), step_id_to_step)

    steps = []
    for step in lesson_steps:
        block = step.get("block", {})
        block_type = block.get("name", "unknown")
        # a step keeps its name under options, and most types have no name at all
        title = block.get("options", {}).get("title") or f"Step {step['id']} ({block_type})"
        steps.append(
            {
                "id": step["id"],
                "position": step["position"],
                "title": title,
                "dir_name": _dir_name("step_", step["position"], block_type),
                "block": block,
                "raw": step,
            }
        )

    title = lesson.get("title", "")
    return {
        "id": lesson["id"],
        "position": position,
        "title": title,
        "dir_name": _dir_name("lesson_", position, title),
        "steps": steps,
    }


def _build_module_node(section, unit_id_to_unit, lesson_id_to_lesson, step_id_to_step):
    module_units = _resolve_ids_to_items(f"module {section['id']}", "unit", section.get("units", []), unit_id_to_unit)

    lessons = []
    for unit in module_units:
        lesson = lesson_id_to_lesson.get(unit["lesson"])
        if lesson is None:
            logger.warning(
                "unit %s (module %s) references lesson %s which could not be resolved, skipping",
                unit["id"],
                section["id"],
                unit["lesson"],
            )
            continue
        lessons.append(_build_lesson_node(lesson, unit["position"], step_id_to_step))

    title = section.get("title", "")
    return {
        "id": section["id"],
        "position": section["position"],
        "title": title,
        "dir_name": _dir_name("module_", section["position"], title),
        "lessons": lessons,
    }


def build_course_tree(client, course_id):
    courses = client.get_by_ids("courses", [course_id])
    if not courses:
        raise CourseNotFoundError(f"Course {course_id} not found or not accessible with current auth scope")
    course = courses[0]

    section_ids = course.get("sections", [])
    section_id_to_section = {section["id"]: section for section in client.get_by_ids("sections", section_ids)}
    sections = _resolve_ids_to_items(f"course {course['id']}", "section", section_ids, section_id_to_section)

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
            _build_module_node(section, unit_id_to_unit, lesson_id_to_lesson, step_id_to_step) for section in sections
        ],
    }
