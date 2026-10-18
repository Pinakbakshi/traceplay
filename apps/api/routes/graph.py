"""
TracePlay Graph Analysis API Routes.
Triggers GitNexus/Graphify code dependency extraction and records graph evidence.
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from apps.api.database import get_db
from apps.api.models import Project, TestRun, GraphEvidence
from apps.api.schemas import GraphAnalyzeRequest
from packages.graph_adapters.code_graph_analyzer import CodeGraphAdapter

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.post("/analyze")
def trigger_graph_analysis(data: GraphAnalyzeRequest, run_id: str = None, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == data.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    adapter = CodeGraphAdapter(engine_name=data.engine)
    paths = adapter.analyze_repository(
        repository_path=project.repository_url or ".",
        commit_sha=data.commit_sha,
        endpoints=data.endpoints,
    )

    if run_id:
        evidence = GraphEvidence(
            run_id=run_id,
            engine=data.engine,
            engine_version=adapter.version,
            indexed_commit=data.commit_sha,
            query_text=f"Impact analysis for {len(paths)} symbols",
            path_json=json.dumps(paths),
            provenance="static_extracted",
            confidence=1.0,
            staleness_status="fresh",
        )
        db.add(evidence)
        db.commit()

    return {
        "status": "success",
        "engine": data.engine,
        "engine_version": adapter.version,
        "indexed_commit": data.commit_sha,
        "extracted_paths_count": len(paths),
        "paths": paths,
    }
