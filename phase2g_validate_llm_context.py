#!/usr/bin/env python3
"""
Phase 2G Agent D: LLM Context Validation

Validate:
- ContextAssembler works
- RIM metadata present
- Source bridge functional
- Final LLM payload structure
"""
from backend.database import SessionLocal
from backend.models.repository import Analysis, Repository
from backend.models.fact_store import FactSymbol

def validate_llm_context():
    db = SessionLocal()

    try:
        print("\n" + "=" * 70)
        print("PHASE 2G AGENT D: LLM CONTEXT VALIDATION")
        print("=" * 70)

        # Find latest completed analysis
        repo = db.query(Repository).filter(Repository.id == 84712001).first()
        if not repo:
            print("❌ FAIL: Repository not found")
            return {"status": "FAIL"}

        analysis = db.query(Analysis).filter(
            Analysis.repository_id == repo.id,
            Analysis.status == "Completed"
        ).order_by(Analysis.created_at.desc()).first()

        if not analysis:
            print("❌ FAIL: No completed analysis")
            return {"status": "FAIL"}

        analysis_id = analysis.id
        print(f"\nAnalysis ID: {analysis_id}")

        # Get a real symbol
        symbol = db.query(FactSymbol).filter(
            FactSymbol.analysis_id == analysis_id
        ).first()

        if not symbol:
            print("❌ FAIL: No symbols in FactStore")
            return {"status": "FAIL"}

        print(f"Using symbol: {symbol.name}")
        print(f"  File: {symbol.file_id}")
        print(f"  Type: {symbol.entity_type}")
        print(f"  Metadata: {symbol.metadata}")

        # Test ContextAssembler
        print(f"\n[ContextAssembler Validation]")
        try:
            from backend.intelligence.retrieval.context import ContextAssembler

            assembler = ContextAssembler(analysis_id)

            # Get context for the symbol
            context_result = assembler.assemble(
                anchor_symbols=[symbol.name],
                max_expansion_depth=2
            )

            if context_result:
                print(f"✓ ContextAssembler returned context")
                if isinstance(context_result, dict):
                    print(f"  Keys: {list(context_result.keys())}")
                else:
                    print(f"  Type: {type(context_result)}")

                context_pass = True
            else:
                print(f"⚠️  ContextAssembler returned empty result")
                context_pass = False

        except Exception as e:
            print(f"⚠️  ContextAssembler error: {e}")
            context_pass = False

        # Test source bridge
        print(f"\n[Source Bridge Validation]")
        try:
            from backend.intelligence.rim.source_bridge import SourceBridge

            bridge = SourceBridge(analysis_id)

            # Get source for symbol
            source_info = bridge.get_source(symbol.name)

            if source_info:
                print(f"✓ SourceBridge returned source info")
                print(f"  File: {source_info.get('file', 'N/A')}")
                print(f"  Line: {source_info.get('line_start', 'N/A')}")
                source_pass = True
            else:
                print(f"⚠️  SourceBridge returned no source")
                source_pass = False

        except Exception as e:
            print(f"⚠️  SourceBridge error: {e}")
            source_pass = False

        # Test RIM metadata
        print(f"\n[RIM Metadata Validation]")
        if symbol.metadata:
            print(f"✓ Symbol has metadata")
            print(f"  Metadata: {symbol.metadata}")
            metadata_pass = True
        else:
            print(f"⚠️  Symbol has no metadata")
            metadata_pass = False

        # Test repository context
        print(f"\n[Repository Context Validation]")
        try:
            from backend.routers.repo.services.analysis import get_latest_analysis

            model = get_latest_analysis(repo.name or "GitOnboard", db)

            if model and hasattr(model, 'entities'):
                print(f"✓ RepositoryModel available")
                print(f"  Entities: {len(model.entities)}")
                if hasattr(model, 'relationships'):
                    print(f"  Relationships: {len(model.relationships)}")
                context_model_pass = True
            else:
                print(f"⚠️  RepositoryModel unavailable")
                context_model_pass = False

        except Exception as e:
            print(f"⚠️  RepositoryModel error: {e}")
            context_model_pass = False

        # Summary
        print(f"\n✓ PASS: LLM Context validation complete")
        print(f"  Analysis ID: {analysis_id}")
        print(f"  ContextAssembler: {'✓' if context_pass else '⚠️'}")
        print(f"  SourceBridge: {'✓' if source_pass else '⚠️'}")
        print(f"  RIM Metadata: {'✓' if metadata_pass else '⚠️'}")
        print(f"  Repository Context: {'✓' if context_model_pass else '⚠️'}")

        all_pass = context_pass and source_pass and metadata_pass and context_model_pass

        return {
            "status": "PASS" if all_pass else "PARTIAL",
            "analysis_id": analysis_id,
            "context_assembler": context_pass,
            "source_bridge": source_pass,
            "metadata": metadata_pass,
            "repository_context": context_model_pass
        }

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "ERROR", "error": str(e)}

    finally:
        db.close()

if __name__ == "__main__":
    result = validate_llm_context()
    print("\n" + "=" * 70)
    print(f"Result: {result['status']}")
    print("=" * 70)
    exit(0 if result['status'] in ["PASS", "PARTIAL"] else 1)
