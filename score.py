import os
import sys
import json

# Fix for Windows Console Unicode errors
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Fix for Python 3.14 Protobuf TypeError
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"

import logging
import csv

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

import argparse

from pdf import PDFHandler
from github import fetch_and_display_github_info
from models import JSONResume, build_evaluation_model, EvaluationData
from typing import List, Optional, Dict
from evaluator import ResumeEvaluator
from roles import Role, load_role, list_available_roles, scaffold_role
from pathlib import Path
from prompt import DEFAULT_MODEL, MODEL_PARAMETERS
from transform import (
    transform_evaluation_response,
    convert_json_resume_to_text,
    convert_github_data_to_text,
    convert_blog_data_to_text,
)
from config import DEVELOPMENT_MODE

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)5s - %(lineno)5d - %(funcName)33s - %(levelname)5s - %(message)s",
)


def print_evaluation_results(
    evaluation, role: str = None, candidate_name: str = "Candidate", *args, **kwargs
):
    """Print evaluation results in a readable format."""
    print("\n" + "=" * 80)
    print(f"📊 RESUME EVALUATION RESULTS FOR: {candidate_name}")
    if role:
        print(f"💼 ROLE: {role}")
    print("=" * 80)

    if not evaluation:
        print("❌ No evaluation data available")
        return

    # Check if eligible field exists
    eligible = getattr(evaluation, "eligible", None)
    if eligible is None and isinstance(evaluation, dict):
        eligible = evaluation.get("eligible")

    if eligible is False:
        print("\n❌ ELIGIBILITY STATUS: REJECTED (Failed Hard Eligibility Filter)")
        print("-" * 60)
        print("Reasons for rejection:")
        reasons = getattr(evaluation, "rejection_reasons", None) or (evaluation.get("rejection_reasons", []) if isinstance(evaluation, dict) else [])
        for reason in reasons:
            print(f"  • {reason}")
        skills = getattr(evaluation, "matched_skills", None) or (evaluation.get("matched_skills", []) if isinstance(evaluation, dict) else [])
        if skills:
            print(f"\nMatched skills found: {', '.join(skills)}")
        print("\n🎯 OVERALL SCORE: 0.0/100 (Ineligible candidates are not ranked)")
        print("\n" + "=" * 80)
        return

    # Calculate or retrieve total score
    total_score = getattr(evaluation, "total_score", None)
    if total_score is None and isinstance(evaluation, dict):
        total_score = evaluation.get("total_score")
    
    # 1. Check if score_breakdown exists
    score_breakdown = getattr(evaluation, "score_breakdown", None) or (evaluation.get("score_breakdown") if isinstance(evaluation, dict) else None)
    if score_breakdown:
        bd = score_breakdown.model_dump() if hasattr(score_breakdown, "model_dump") else score_breakdown
        if isinstance(bd, dict):
            if total_score is None:
                total_score = sum(
                    (v if isinstance(v, (int, float)) else v.get("score", 0))
                    for v in bd.values() if isinstance(v, (int, float, dict))
                )

            print(f"\n🎯 OVERALL SCORE: {total_score:.1f}/100")
            print("\n📈 DETAILED SCORES (100 Points Max):")
            print("-" * 60)
            
            categories = [
                ("ai_project_depth", "🤖 AI / Agentic / RAG Project Depth", 40),
                ("python_backend", "🐍 Python & Backend Engineering", 30),
                ("cloud_fullstack", "☁️ Cloud / Deployment / Full Stack", 15),
                ("github", "🐙 GitHub Activity", 10),
                ("engineering_depth", "⚙️ Engineering Depth Signals", 5),
            ]
            
            for key, label, default_max in categories:
                item = bd.get(key, {})
                if isinstance(item, (int, float)):
                    score_val = item
                    max_val = default_max
                    evidence = ""
                else:
                    score_val = item.get("score", 0)
                    max_val = item.get("max", default_max)
                    evidence = item.get("evidence", "")
                
                print(f"{label}: {score_val:.1f}/{max_val}")
                if evidence:
                    print(f"   Evidence: {evidence}")
                print()

    # 2. Check if legacy scores dict exists
    elif hasattr(evaluation, "scores") or (isinstance(evaluation, dict) and "scores" in evaluation):
        scores = getattr(evaluation, "scores", None) or evaluation.get("scores")
        items = scores.model_dump() if hasattr(scores, "model_dump") else scores
        if isinstance(items, dict):
            if total_score is None:
                total_score = sum(v["score"] for v in items.values() if isinstance(v, dict) and "score" in v)

            print(f"\n🎯 OVERALL SCORE: {total_score:.1f}/100")
            print("\n📈 DETAILED SCORES (100 Points Max):")
            print("-" * 60)
            for cat_name, cat_data in items.items():
                if isinstance(cat_data, dict):
                    label = cat_name.replace("_", " ").title()
                    print(f"• {label}: {cat_data.get('score', 0)}/{cat_data.get('max', 0)}")
                    if cat_data.get("evidence"):
                        print(f"  Evidence: {cat_data.get('evidence', '')}")
                    print()

    # Strengths & areas for improvement
    strengths = getattr(evaluation, "strengths", None) or getattr(evaluation, "key_strengths", None) or (evaluation.get("strengths") or evaluation.get("key_strengths") if isinstance(evaluation, dict) else [])
    if strengths:
        print("✅ KEY STRENGTHS:")
        print("-" * 30)
        for i, s in enumerate(strengths, 1):
            print(f"  {i}. {s}")
        print()

    concerns = getattr(evaluation, "concerns", None) or getattr(evaluation, "areas_for_improvement", None) or (evaluation.get("concerns") or evaluation.get("areas_for_improvement") if isinstance(evaluation, dict) else [])
    if concerns:
        print("🔧 AREAS FOR IMPROVEMENT / CONCERNS:")
        print("-" * 30)
        for i, c in enumerate(concerns, 1):
            print(f"  {i}. {c}")

    print("\n" + "=" * 80)


def _evaluate_resume(
    resume_data: JSONResume,
    role: Role,
    evaluation_model,
    github_data: dict = None,
    blog_data: dict = None,
):
    """Evaluate the resume using AI and display results."""

    model_params = MODEL_PARAMETERS.get(DEFAULT_MODEL)
    evaluator = ResumeEvaluator(
        role=role,
        evaluation_model=evaluation_model,
        model_name=DEFAULT_MODEL,
        model_params=model_params,
    )

    # Convert JSON resume data to text
    resume_text = convert_json_resume_to_text(resume_data)

    # Add GitHub data if available
    if github_data:
        github_text = convert_github_data_to_text(github_data)
        resume_text += github_text

    # Add blog data if available
    if blog_data:
        blog_text = convert_blog_data_to_text(blog_data)
        resume_text += blog_text

    # Evaluate the enhanced resume
    evaluation_result = evaluator.evaluate_resume(resume_text)

    # print(evaluation_result)

    return evaluation_result


def is_valid_resume_data(resume_data: JSONResume) -> bool:
    """Check if the resume data has at least some extracted core content."""
    if not resume_data:
        return False
    core_sections = [
        resume_data.basics,
        resume_data.work,
        resume_data.education,
        resume_data.skills,
        resume_data.projects,
    ]
    return any(section is not None for section in core_sections)


def find_profile(profiles, network):
    if not profiles:
        return None
    return next(
        (p for p in profiles if p.network and p.network.lower() == network.lower()),
        None,
    )


def main(pdf_path, role: Role):
    if isinstance(role, str):
        if "load_role" in globals():
            role = load_role(role)
        elif "get_role" in globals():
            role = get_role(role)
    evaluation_model = build_evaluation_model(role)

    # Create cache filename based on PDF path
    cache_filename = (
        f"cache/resumecache_{os.path.basename(pdf_path).replace('.pdf', '')}.json"
    )
    github_cache_filename = (
        f"cache/githubcache_{os.path.basename(pdf_path).replace('.pdf', '')}.json"
    )

    resume_data = None
    cache_loaded = False

    # Check if cache exists and we're in development mode
    if DEVELOPMENT_MODE and os.path.exists(cache_filename):
        print(f"Loading cached data from {cache_filename}")
        try:
            cached_data = json.loads(Path(cache_filename).read_text(encoding="utf-8"))
            loaded_resume = JSONResume(**cached_data)
            if not is_valid_resume_data(loaded_resume):
                raise ValueError("Cached resume data contains no core content")
            resume_data = loaded_resume
            cache_loaded = True
        except Exception as e:
            print(f"⚠️ Warning: Invalid cache file {cache_filename}: {e}")
            print("Ignoring cache and reprocessing PDF...")
            try:
                os.remove(cache_filename)
            except Exception as delete_err:
                print(
                    f"Failed to delete invalid cache file {cache_filename}: {delete_err}"
                )

    if not cache_loaded:
        logger.debug(
            f"Extracting data from PDF"
            + (" and caching to " + cache_filename if DEVELOPMENT_MODE else "")
        )
        pdf_handler = PDFHandler()
        resume_data = pdf_handler.extract_json_from_pdf(pdf_path)

        if resume_data == None:
            return None

        if DEVELOPMENT_MODE:
            if is_valid_resume_data(resume_data):
                os.makedirs(os.path.dirname(cache_filename), exist_ok=True)
                Path(cache_filename).write_text(
                    json.dumps(resume_data.model_dump(), indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            else:
                logger.warning(
                    "Newly extracted resume data is empty/invalid. Skipping cache write."
                )

    # Check if cache exists and we're in development mode
    github_data = {}
    github_cache_loaded = False
    if DEVELOPMENT_MODE and os.path.exists(github_cache_filename):
        print(f"Loading cached data from {github_cache_filename}")
        try:
            loaded_github = json.loads(
                Path(github_cache_filename).read_text(encoding="utf-8")
            )
            if (
                not isinstance(loaded_github, dict)
                or not loaded_github
                or "profile" not in loaded_github
            ):
                raise ValueError("Cached GitHub data is invalid or empty")
            github_data = loaded_github
            github_cache_loaded = True
        except Exception as e:
            print(f"⚠️ Warning: Invalid GitHub cache file {github_cache_filename}: {e}")
            print("Ignoring GitHub cache and refetching...")
            try:
                os.remove(github_cache_filename)
            except Exception as delete_err:
                print(
                    f"Failed to delete invalid GitHub cache file {github_cache_filename}: {delete_err}"
                )

    if not github_cache_loaded:
        # Add validation to handle None values
        profiles = []
        if resume_data and hasattr(resume_data, "basics") and resume_data.basics:
            profiles = resume_data.basics.profiles or []
        github_profile = find_profile(profiles, "Github")

        if github_profile:
            print(
                f"Fetching GitHub data"
                + (
                    " and caching to " + github_cache_filename
                    if DEVELOPMENT_MODE
                    else ""
                )
            )
            github_data = fetch_and_display_github_info(
                github_profile.url, position_title=role.position_title
            )

            if (
                DEVELOPMENT_MODE
                and github_data
                and isinstance(github_data, dict)
                and "profile" in github_data
            ):
                os.makedirs(os.path.dirname(github_cache_filename), exist_ok=True)
                Path(github_cache_filename).write_text(
                    json.dumps(github_data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )

    score = _evaluate_resume(resume_data, role, evaluation_model, github_data)

    # Get candidate name for display
    candidate_name = os.path.basename(pdf_path).replace(".pdf", "")
    if (
        resume_data
        and hasattr(resume_data, "basics")
        and resume_data.basics
        and resume_data.basics.name
    ):
        candidate_name = resume_data.basics.name

    # Print evaluation results in readable format
    print_evaluation_results(score, role, candidate_name)

    if DEVELOPMENT_MODE:
        csv_row = transform_evaluation_response(
            file_name=os.path.basename(pdf_path),
            evaluation=score,
            resume_data=resume_data,
            github_data=github_data,
            role=role,
        )

        # Write CSV row to a role-specific file, since each role's columns differ.
        csv_path = f"resume_evaluations_{role.name}.csv"
        file_exists = os.path.exists(csv_path)

        with open(csv_path, "a", newline="", encoding="utf-8") as csvfile:
            fieldnames = list(csv_row.keys())
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            # Write headers if file doesn't exist
            if not file_exists:
                writer.writeheader()

            # Write the row
            writer.writerow(csv_row)

    return score


if __name__ == "__main__":
    available_roles = list_available_roles()
    parser = argparse.ArgumentParser(
        description="Score a resume against a role's rubric."
    )
    parser.add_argument(
        "pdf_path", nargs="?", help="Path to the resume PDF to evaluate"
    )
    parser.add_argument(
        "--role",
        help="Role to score against (a directory name under roles/). "
        + (f"Available: {', '.join(available_roles)}" if available_roles else ""),
    )
    parser.add_argument(
        "--init-role",
        metavar="NAME",
        help="Scaffold a new role directory under roles/ with basic template "
        "files, then exit (does not score a resume).",
    )
    args = parser.parse_args()

    # Scaffold mode: create a new role and exit.
    if args.init_role:
        try:
            role_dir = scaffold_role(args.init_role)
        except ValueError as e:
            print(f"Error: {e}")
            exit(1)
        print(f"✅ Created role '{args.init_role}' at {role_dir}")
        print("   Edit role.json, criteria.jinja and system_message.jinja, then run:")
        print(f"   python score.py <pdf_path> --role {args.init_role}")
        exit(0)

    # Scoring mode: both pdf_path and --role are required.
    if not args.pdf_path or not args.role:
        parser.error("pdf_path and --role are required (or use --init-role NAME)")

    if not os.path.exists(args.pdf_path):
        print(f"Error: File '{args.pdf_path}' does not exist.")
        exit(1)

    try:
        role = load_role(args.role)
    except ValueError as e:
        print(f"Error: {e}")
        exit(1)

    main(args.pdf_path, role)
