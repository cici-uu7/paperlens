from app.core.config import get_settings
from app.models.schemas import AskResponse, Citation, RetrievalMetadata
from app.services.eval_service import EvaluationService


class StubAnswerService:
    def __init__(self, responses):
        self.responses = responses

    def answer_question(self, question, top_k=None):
        response = self.responses[question]
        if isinstance(response, Exception):
            raise response
        return response


def test_evaluation_service_runs_and_writes_outputs(tmp_path):
    env_path = tmp_path / '.env'
    env_path.write_text('', encoding='utf-8')
    settings = get_settings(project_root=tmp_path, env_path=env_path)
    settings.ensure_runtime_dirs()

    questions_path = settings.eval_dir / 'questions.csv'
    questions_path.write_text(
        '\n'.join(
            [
                'id,question_type,answerability,question,gold_doc,gold_page_hint,gold_answer',
                'Q01,normal,answerable,What is LayoutLM?,layoutlm.pdf,2,It models text and layout.',
                'Q02,normal,unanswerable,What is the 2026 GPU price?,NOT_FOUND,NA,Should refuse.',
                'Q03,normal,answerable,Will this error?,layoutlm.pdf,1,Should record exception.',
                'Q04,compare,answerable,Which papers are compared?,layoutlm.pdf|docllm.pdf,1|2,Either cited doc should count as a hit.',
            ]
        ),
        encoding='utf-8-sig',
    )

    responses = {
        'What is LayoutLM?': AskResponse(
            question='What is LayoutLM?',
            answer='It models text and layout.',
            answerable=True,
            citations=[Citation(doc_name='layoutlm.pdf', page_num=2, chunk_id='c1', quote='evidence')],
            retrieval=RetrievalMetadata(top_k=5, hit_count=1, latency_ms=12.0),
            failure_reason=None,
        ),
        'What is the 2026 GPU price?': AskResponse(
            question='What is the 2026 GPU price?',
            answer='The retrieved context is not sufficient to answer this question reliably.',
            answerable=False,
            citations=[],
            retrieval=RetrievalMetadata(top_k=5, hit_count=0, latency_ms=8.0),
            failure_reason='insufficient_context',
        ),
        'Will this error?': RuntimeError('boom'),
        'Which papers are compared?': AskResponse(
            question='Which papers are compared?',
            answer='DocLLM is part of the comparison.',
            answerable=True,
            citations=[Citation(doc_name='docllm.pdf', page_num=2, chunk_id='c2', quote='comparison')],
            retrieval=RetrievalMetadata(top_k=5, hit_count=1, latency_ms=9.0),
            failure_reason=None,
        ),
    }

    service = EvaluationService(StubAnswerService(responses), settings)
    results, summary, paths = service.run_full_evaluation(questions_path=questions_path)

    assert len(results) == 4
    assert summary.total_questions == 4
    assert summary.answered_count == 2
    assert summary.refusal_count == 1
    assert summary.error_count == 1
    assert summary.doc_hit_count == 3
    assert summary.citation_rate > 0
    assert results[-1].expected_doc_hit is True
    assert paths['results_csv'].exists()
    assert paths['summary_md'].exists()
    assert paths['run_log'].exists()

    csv_text = paths['results_csv'].read_text(encoding='utf-8-sig')
    summary_text = paths['summary_md'].read_text(encoding='utf-8')
    run_log_text = paths['run_log'].read_text(encoding='utf-8')

    assert 'Q01' in csv_text
    assert 'Q04' in csv_text
    assert 'answerability_mismatch' not in summary_text
    assert 'Q03' in summary_text
    assert 'boom' in run_log_text
