"""Run a small local RAG quality check against a user-curated JSON question set."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal
from app.models.rbac import User
from app.models.sharing import DocumentGrant
from app.services.qa import answer_question


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path, help="JSON file with a cases array")
    parser.add_argument("--username", required=True, help="Account whose document permissions are evaluated")
    parser.add_argument("--report", type=Path, help="Optional path for a JSON report")
    args = parser.parse_args()
    payload = json.loads(args.cases.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    if not cases:
        raise SystemExit("The cases file must contain at least one case.")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == args.username).first()
        if user is None:
            raise SystemExit(f"Account not found: {args.username}")
        shared_ids = []
        if user.role.name.casefold() != "admin":
            shared_ids = [item[0] for item in db.query(DocumentGrant.document_id).filter(DocumentGrant.user_id == user.id).all()]
        results = []
        for case in cases:
            response = answer_question(case["question"], user, tag=case.get("tag"), shared_document_ids=shared_ids)
            answer = response["answer"].casefold()
            terms = [str(term).casefold() for term in case.get("expected_terms", [])]
            source_hint = str(case.get("expected_source", "")).casefold()
            source_match = any(source_hint in source["filename"].casefold() for source in response["sources"]) if source_hint else None
            matched_terms = [term for term in terms if term in answer]
            term_coverage = len(matched_terms) / len(terms) if terms else None
            results.append({
                "question": case["question"], "answer": response["answer"],
                "sources": [{"filename": item["filename"], "chunk": item["chunk"]} for item in response["sources"]],
                "expected_source_match": source_match,
                "expected_terms_match": bool(terms) and len(matched_terms) == len(terms),
                "expected_term_coverage": term_coverage,
                "matched_terms": matched_terms,
            })
        term_scores = [row["expected_term_coverage"] for row in results if row["expected_term_coverage"] is not None]
        source_scores = [row["expected_source_match"] for row in results if row["expected_source_match"] is not None]
        report = {
            "account": user.username, "case_count": len(results), "results": results,
            "source_match_rate": sum(source_scores) / len(source_scores) if source_scores else None,
            "mean_expected_term_coverage": sum(term_scores) / len(term_scores) if term_scores else None,
            "metric_note": "Exact expected-source and phrase checks are screening heuristics. Review answers and excerpts manually; these scores do not prove factual correctness.",
        }
        rendered = json.dumps(report, indent=2, ensure_ascii=False)
        print(rendered)
        if args.report:
            args.report.write_text(rendered + "\n", encoding="utf-8")
            print(f"Saved report to {args.report}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
