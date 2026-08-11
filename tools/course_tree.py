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

from stepik_client import StepikClient

logger = logging.getLogger("stepik_export")

MAX_SLUG_LEN = 50
DIR_INDEX_WIDTH = 3


def _dir_name(index, title, prefix=""):
    slug = slugify(title or "untitled", max_length=MAX_SLUG_LEN)
    return f"{prefix}{index:0{DIR_INDEX_WIDTH}d}_{slug}"


def build_course_tree(client: StepikClient, course_id: int) -> dict:
    courses = client.get_by_ids("courses", [course_id])
    if not courses:
        raise ValueError(f"Course {course_id} not found or not accessible with current auth scope")
    course = courses[0]

    sections = client.get_by_ids("sections", course.get("sections", []))
    sections.sort(key=lambda s: s.get("position", 0))

    all_unit_ids = [uid for s in sections for uid in s.get("units", [])]
    units = client.get_by_ids("units", all_unit_ids)
    unit_id_to_unit = {u["id"]: u for u in units}

    lesson_ids = [unit_id_to_unit[uid]["lesson"] for uid in all_unit_ids if uid in unit_id_to_unit]
    lessons = client.get_by_ids("lessons", lesson_ids)
    lesson_id_to_lesson = {lesson["id"]: lesson for lesson in lessons}

    all_step_ids = [sid for lesson in lessons for sid in lesson.get("steps", [])]
    steps = client.get_by_ids("steps", all_step_ids)
    step_id_to_step = {st["id"]: st for st in steps}

    course_slug = slugify(course.get("title", "course"), max_length=MAX_SLUG_LEN)
    tree = {
        "id": course["id"],
        "title": course.get("title", ""),
        "dir_name": f"{course['id']}_{course_slug}",
        "modules": [],
    }

    for m_idx, section in enumerate(sections, start=1):
        module_units = []
        for uid in section.get("units", []):
            unit = unit_id_to_unit.get(uid)
            if unit is None:
                logger.warning(
                    "module %s references unit %s which could not be resolved, skipping",
                    section.get("id"),
                    uid,
                )
                continue
            module_units.append(unit)
        module_units.sort(key=lambda u: u.get("position", 0))

        module_node = {
            "id": section["id"],
            "title": section.get("title", ""),
            "dir_name": _dir_name(m_idx, section.get("title"), prefix="module_"),
            "lessons": [],
        }

        for l_idx, unit in enumerate(module_units, start=1):
            lesson = lesson_id_to_lesson.get(unit.get("lesson"))
            if lesson is None:
                logger.warning(
                    "unit %s (module %s) references lesson %s which could not be resolved, skipping",
                    unit.get("id"),
                    section.get("id"),
                    unit.get("lesson"),
                )
                continue

            lesson_step_ids = lesson.get("steps", [])
            lesson_steps = []
            for sid in lesson_step_ids:
                step = step_id_to_step.get(sid)
                if step is None:
                    logger.warning(
                        "lesson %s references step %s which could not be resolved, skipping",
                        lesson["id"],
                        sid,
                    )
                    continue
                lesson_steps.append(step)
            lesson_steps.sort(key=lambda st: st.get("position", 0))

            lesson_node = {
                "id": lesson["id"],
                "title": lesson.get("title", ""),
                "dir_name": _dir_name(l_idx, lesson.get("title"), prefix="lesson_"),
                "steps": [],
            }

            for s_idx, step in enumerate(lesson_steps, start=1):
                lesson_node["steps"].append(
                    {
                        "id": step["id"],
                        "dir_name": _dir_name(s_idx, step.get("block", {}).get("name", "step"), prefix="step_"),
                        "block": step.get("block", {}),
                        "raw": step,
                    }
                )

            module_node["lessons"].append(lesson_node)

        tree["modules"].append(module_node)

    return tree
