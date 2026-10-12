import asyncio
import json
import time
import os
import sys

from backend.services.qa_loop import QALoop
from backend.services.qa_protocol import QAProtocolAdapter
from backend.agent.loop.contracts import AgentLoopConfig
from backend.repository_tools.tools import RepositoryToolLayer
from backend.services.tool_dispatch import ToolDispatchTable
from backend.database import SessionLocal
from backend.ai.service import get_llm_service
from backend.ai.schemas import Message, MessageRole, LLMRequest

async def run_test7_benchmark():
    print("[TEST 7] Starting DGB01 benchmark execution...")
    db = SessionLocal()
    try:
        tool_layer = RepositoryToolLayer('Deep-Guard-Integrated-Backend', db=db, analysis_id=5)
        tool_dispatch = ToolDispatchTable(tool_layer)
        llm_service = get_llm_service()
        protocol_adapter = QAProtocolAdapter(model_id='qwen3:4b-instruct', provider='ollama')
        prompt_parts = protocol_adapter.build_system_prompt(
            tool_specs=tool_dispatch.specs(include_rim=False),
            rim_metadata_block=''
        )
        config = AgentLoopConfig(
            max_agent_turns=12,
            max_tool_calls=10,
        )

        final_request_captured = {}
        raw_response_captured = ""
        original_generate = llm_service.generate

        async def intercept_generate(request, *args, **kwargs):
            nonlocal final_request_captured, raw_response_captured
            is_final = False
            for m in request.messages:
                if 'complete, final answer in Markdown' in (m.content or ''):
                    is_final = True
                    break
            if is_final:
                final_request_captured = {
                    'model': request.model,
                    'temperature': request.temperature,
                    'max_tokens': request.max_tokens,
                    'messages': [{'role': m.role.value if hasattr(m.role, 'value') else str(m.role), 'content': m.content} for m in request.messages]
                }
            resp = await original_generate(request, *args, **kwargs)
            if is_final:
                raw_response_captured = resp.content
            return resp

        llm_service.generate = intercept_generate

        loop = QALoop(
            llm_service=llm_service,
            tool_dispatch=tool_dispatch,
            config=config,
            system_prompt_parts=prompt_parts,
            model='qwen3:4b-instruct',
            provider='ollama',
            repository='Deep-Guard-Integrated-Backend',
            mode='baseline',
        )

        query = "Trace how user authentication, JWT access tokens, refresh tokens, and device sessions are created, stored, and rotated in the backend. Where are refresh tokens persisted in Supabase, how is the device fingerprint calculated, and how does the server prevent token reuse or replay attacks?"
        
        start_time = time.time()
        result = await loop.run(query)
        elapsed = time.time() - start_time

        print(f"[TEST 7] Completed in {elapsed:.2f}s. Stop reason: {result.stop_reason}, Tool calls: {result.tool_call_count}")

        files_read = []
        files_searched = []
        turns_data = []
        for t in result.turns:
            tc = t.tool_call
            obs = t.tool_observation
            if tc:
                tname = tc.get('tool_name') or tc.get('name') or ''
                args = tc.get('arguments') or tc.get('args') or {}
                if 'read_file' in tname and 'path' in args:
                    if args['path'] not in files_read:
                        files_read.append(args['path'])
                elif 'search' in tname:
                    q_term = args.get('query')
                    if q_term and q_term not in files_searched:
                        files_searched.append(q_term)
            turns_data.append({
                'turn_index': t.turn_index,
                'tool_call': t.tool_call,
                'tool_observation': {
                    'tool_name': obs.get('tool_name') if obs else None,
                    'success': obs.get('success') if obs else None,
                    'error': obs.get('error') if obs else None,
                    'data_preview': str(obs.get('data'))[:300] if obs and obs.get('data') else None
                } if obs else None,
                'prompt_tokens': t.prompt_tokens,
                'completion_tokens': t.completion_tokens,
                'duration_ms': t.duration_ms
            })

        output = {
            'run_id': 'test7_evidence_coverage_run',
            'stop_reason': str(result.stop_reason),
            'tool_call_count': result.tool_call_count,
            'files_read': files_read,
            'files_searched': files_searched,
            'elapsed_seconds': elapsed,
            'answer': result.answer,
            'raw_response': raw_response_captured,
            'final_request': final_request_captured,
            'turns': turns_data
        }

        with open('/tmp/test7_run_result.json', 'w') as f:
            json.dump(output, f, indent=2)
        print('TEST7_EXECUTION_COMPLETED_SUCCESSFULLY')
    finally:
        db.close()

if __name__ == '__main__':
    asyncio.run(run_test7_benchmark())
