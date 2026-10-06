"""
Batch Resume Screening and Ranking System
Evaluates an entire folder of PDF resumes according to the SDE Intern + AI rubric.
Produces ranked results in JSON, with incremental saving and error resilience.

Usage:
    python main.py --input ./resume --output ./output/results.json --role software_engineering_intern
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("batch_evaluator")


def find_pdf_resumes(input_dir: str) -> List[str]:
    """Find all PDF files in the specified directory."""
    path = Path(input_dir)
    if not path.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")
    
    pdf_files = sorted(list(path.glob("*.pdf")) + list(path.glob("**/*.pdf")))
    seen = set()
    unique_pdfs = []
    for p in pdf_files:
        resolved = str(p.resolve())
        if resolved not in seen:
            seen.add(resolved)
            unique_pdfs.append(str(p))
    
    return unique_pdfs


def extract_candidate_record(score_result: Any, pdf_path: str) -> Dict[str, Any]:
    """Convert score result into the standardized assignment JSON structure."""
    file_name = os.path.basename(pdf_path)
    default_name = file_name.replace(".pdf", "").replace("_", " ").title()

    if score_result is None:
        return {
            "candidate_name": default_name,
            "file_name": file_name,
            "eligible": False,
            "rejection_reasons": ["Failed to extract or evaluate resume."],
            "total_score": 0,
            "score_breakdown": {
                "ai_project_depth": 0,
                "python_backend": 0,
                "cloud_fullstack": 0,
                "github": 0,
                "engineering_depth": 0,
            },
            "matched_skills": [],
            "project_summary": "",
            "github_summary": "Not available",
            "github_enrichment_status": "failed",
            "strengths": [],
            "concerns": ["Unreadable or failed evaluation."],
        }

    data = score_result.model_dump() if hasattr(score_result, "model_dump") else score_result
    if not isinstance(data, dict):
        data = {}

    candidate_name = data.get("candidate_name") or data.get("candidate") or default_name
    eligible = bool(data.get("eligible", True))
    rejection_reasons = data.get("rejection_reasons", [])

    bd_raw = data.get("score_breakdown", {})
    scores_raw = data.get("scores", {})

    def get_val(key_new, key_old, default_max):
        if key_new in bd_raw:
            v = bd_raw[key_new]
            return int(round(v if isinstance(v, (int, float)) else v.get("score", 0)))
        if key_old in scores_raw:
            v = scores_raw[key_old]
            return int(round(v if isinstance(v, (int, float)) else v.get("score", 0)))
        return 0

    ai_depth = get_val("ai_project_depth", "ai_fluency", 40)
    if ai_depth == 0 and "self_projects" in scores_raw and scores_raw["self_projects"].get("max") == 40:
        ai_depth = int(round(scores_raw["self_projects"].get("score", 0)))

    py_backend = get_val("python_backend", "technical_skills", 30)
    cloud_full = get_val("cloud_fullstack", "production", 15)
    github_sc = get_val("github", "open_source", 10)
    eng_depth = get_val("engineering_depth", "self_projects", 5)

    if eligible:
        total_score = data.get("total_score")
        if total_score is None or total_score == 0:
            total_score = ai_depth + py_backend + cloud_full + github_sc + eng_depth
        total_score = int(round(total_score))
    else:
        total_score = 0
        ai_depth = py_backend = cloud_full = github_sc = eng_depth = 0

    matched_skills = data.get("matched_skills", [])
    project_summary = data.get("project_summary", "")
    github_summary = data.get("github_summary", "")
    enrichment_status = data.get("github_enrichment_status", "not_available")
    strengths = data.get("strengths", []) or data.get("key_strengths", [])
    concerns = data.get("concerns", []) or data.get("areas_for_improvement", [])

    return {
        "candidate_name": candidate_name,
        "file_name": file_name,
        "eligible": eligible,
        "rejection_reasons": rejection_reasons,
        "total_score": total_score,
        "score_breakdown": {
            "ai_project_depth": ai_depth,
            "python_backend": py_backend,
            "cloud_fullstack": cloud_full,
            "github": github_sc,
            "engineering_depth": eng_depth,
        },
        "matched_skills": matched_skills,
        "project_summary": project_summary,
        "github_summary": github_summary,
        "github_enrichment_status": enrichment_status,
        "strengths": strengths,
        "concerns": concerns,
    }


def save_incremental_results(records: List[Dict[str, Any]], output_path: str):
    """Save sorted & ranked results to the output JSON file incrementally."""
    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    eligible = [r for r in records if r.get("eligible")]
    rejected = [r for r in records if not r.get("eligible")]

    eligible.sort(key=lambda x: x.get("total_score", 0), reverse=True)

    final_list = []
    for rank_idx, cand in enumerate(eligible, 1):
        cand_copy = dict(cand)
        cand_copy["rank"] = rank_idx
        final_list.append(cand_copy)

    for cand in rejected:
        cand_copy = dict(cand)
        cand_copy["rank"] = None
        final_list.append(cand_copy)

    out_file.write_text(json.dumps(final_list, indent=2, ensure_ascii=False), encoding="utf-8")


def print_batch_summary(records: List[Dict[str, Any]], failed_count: int):
    """Print the required Batch Summary table."""
    total = len(records)
    eligible = [r for r in records if r.get("eligible")]
    rejected = [r for r in records if not r.get("eligible") and r.get("file_name")]
    
    print("\n" + "=" * 80)
    print("📊 BATCH SCREENING & RANKING SUMMARY")
    print("=" * 80)
    print(f"📁 Total Resumes Found:        {total}")
    print(f"✅ Successfully Evaluated:     {total - failed_count}")
    print(f"🎯 Eligible Candidates:       {len(eligible)}")
    print(f"❌ Ineligible / Rejected:      {len(rejected)}")
    print(f"⚠️  Failed / Unreadable:        {failed_count}")
    print("=" * 80)

    if eligible:
        print("\n🏆 TOP RANKED CANDIDATES SHORTLIST:")
        print(f"{'Rank':<6}{'Score':<8}{'Candidate Name':<28}{'Highlights'}")
        print("-" * 80)
        for cand in sorted(eligible, key=lambda x: x.get("total_score", 0), reverse=True)[:10]:
            skills_preview = ", ".join(cand.get("matched_skills", [])[:4])
            if not skills_preview:
                skills_preview = cand.get("project_summary", "")[:45]
            print(f"#{cand.get('rank', '-'):<5}{cand.get('total_score', 0):<8}{cand.get('candidate_name', 'Unknown')[:26]:<28}{skills_preview}")

    if rejected:
        print("\n❌ REJECTED CANDIDATES (Sample):")
        print("-" * 80)
        for cand in rejected[:5]:
            reasons = "; ".join(cand.get("rejection_reasons", [])) or "Did not meet hard criteria"
            print(f"• {cand.get('candidate_name', 'Candidate')}: {reasons}")
    print("\n" + "=" * 80 + "\n")


def run_batch_evaluation(
    input_dir: str,
    output_path: str,
    role_name: str = "software_engineering_intern",
):
    """Execute batch evaluation of all resumes in the input directory."""
    pdf_files = find_pdf_resumes(input_dir)
    total_files = len(pdf_files)

    if total_files == 0:
        logger.warning(f"No PDF files found in {input_dir}")
        return

    logger.info(f"🚀 Found {total_files} resume(s) in '{input_dir}'. Starting batch processing for role '{role_name}'...")

    try:
        import score as score_module
    except ImportError as e:
        logger.error(f"Failed to import score module: {e}")
        return

    # Automatically resolve Role object if a loader function exists in score or role module
    role_obj = role_name
    for loader_name in ["load_role", "get_role", "find_role"]:
        if hasattr(score_module, loader_name):
            try:
                role_obj = getattr(score_module, loader_name)(role_name)
                logger.info(f"Loaded Role configuration for '{role_name}'")
                break
            except Exception as e:
                logger.warning(f"Could not load role via {loader_name}: {e}")

    processed_records: List[Dict[str, Any]] = []
    failed_count = 0

    for idx, pdf_path in enumerate(pdf_files, 1):
        file_name = os.path.basename(pdf_path)
        print(f"\n[{idx}/{total_files}] Processing: {file_name}...")

        try:
            import inspect
            sig = inspect.signature(score_module.main)
            if len(sig.parameters) >= 2:
                score_res = score_module.main(pdf_path, role_obj)
            else:
                score_res = score_module.main(pdf_path)

            record = extract_candidate_record(score_res, pdf_path)
            processed_records.append(record)

            status_icon = "✅ Passed" if record.get("eligible") else "❌ Rejected"
            score_str = f"Score: {record.get('total_score')}/100" if record.get("eligible") else "Score: 0 (Ineligible)"
            print(f"   ↳ {status_icon} | {record.get('candidate_name')} | {score_str}")

        except Exception as e:
            failed_count += 1
            logger.error(f"❌ Error processing '{file_name}': {str(e)}", exc_info=False)
            
            failed_record = {
                "candidate_name": file_name.replace(".pdf", ""),
                "file_name": file_name,
                "eligible": False,
                "rejection_reasons": [f"Unreadable or processing error: {str(e)}"],
                "total_score": 0,
                "score_breakdown": {
                    "ai_project_depth": 0,
                    "python_backend": 0,
                    "cloud_fullstack": 0,
                    "github": 0,
                    "engineering_depth": 0,
                },
                "matched_skills": [],
                "project_summary": "",
                "github_summary": "Not available",
                "github_enrichment_status": "failed",
                "strengths": [],
                "concerns": ["Failed to parse resume file."],
            }
            processed_records.append(failed_record)

        # Save progress incrementally after each candidate
        save_incremental_results(processed_records, output_path)

    print_batch_summary(processed_records, failed_count)
    logger.info(f"💾 Full results saved successfully to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Batch evaluate resume PDFs against the SDE Intern + AI screening rubric."
    )
    parser.add_argument(
        "--input",
        "-i",
        default="./resume",
        help="Input folder containing PDF resumes (default: ./resume or ./resumes)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="./output/results.json",
        help="Output JSON file path (default: ./output/results.json)",
    )
    parser.add_argument(
        "--role",
        "-r",
        default="software_engineering_intern",
        help="Target job role to score against (default: software_engineering_intern)",
    )

    args = parser.parse_args()

    input_path = args.input
    if not os.path.exists(input_path) and os.path.exists("./resumes"):
        input_path = "./resumes"

    run_batch_evaluation(
        input_dir=input_path,
        output_path=args.output,
        role_name=args.role,
    )


if __name__ == "__main__":
    main()