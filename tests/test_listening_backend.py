"""Exercise real backend handlers in memory without writing to the collection."""
import importlib.util
import json
import pathlib
import unittest
import threading
import urllib.request
import os

SOURCE = pathlib.Path(os.environ.get('LEXIS_BACKEND_PATH', str(pathlib.Path(__file__).resolve().parents[1] / 'vocab_review_server.py')))
spec = importlib.util.spec_from_file_location('lexis_backend_under_test', SOURCE)
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class ListeningBackendTests(unittest.TestCase):
    def setUp(self):
        backend.KNOWLEDGE_MAP = {'mapa_vocabulario': {}, 'estatisticas': {}}
        backend.save_knowledge_map_memory = lambda: None
        backend.get_deck_progress = lambda deck: {'subdeck': deck}
        self.responses = []
        self.handler = object.__new__(backend.RequestHandler)
        self.handler.send_json = lambda data, status=200: self.responses.append((status, data))

    def evaluate(self, **overrides):
        payload = dict(id='listening_abc', word='We were ready.', status='desconhecido',
                       pos='LISTENING', subdeck='listening-studio',
                       definition_en='Frase de Listening: We were ready.',
                       definition_pt='', example_1='We were ready.')
        payload.update(overrides)
        self.handler.handle_api_evaluate(payload)
        return self.responses[-1]

    def test_queue_text_is_preserved(self):
        status, result = self.evaluate()
        self.assertEqual(status, 200)
        self.assertTrue(result['success'])
        entry = backend.KNOWLEDGE_MAP['mapa_vocabulario']['we were ready.']['acepcoes'][0]
        self.assertEqual(entry['frase_exemplo'], 'We were ready.')
        self.assertEqual(entry['pos'], 'LISTENING')

    def test_retry_is_idempotent(self):
        self.evaluate()
        self.evaluate()
        entry = backend.KNOWLEDGE_MAP['mapa_vocabulario']['we were ready.']
        self.assertEqual(len(entry['acepcoes']), 1)

    def test_distinct_sentences_with_same_prefix_do_not_collide(self):
        self.evaluate(word='I want to learn.', definition_en='Frase de Listening: I want to learn.')
        self.evaluate(id='listening_def', word='I want to leave.', definition_en='Frase de Listening: I want to leave.')
        self.assertEqual(len(backend.KNOWLEDGE_MAP['mapa_vocabulario']), 2)

    def test_invalid_request_has_no_mutation(self):
        status, _ = self.evaluate(word='')
        self.assertEqual(status, 400)
        self.assertEqual(backend.KNOWLEDGE_MAP['mapa_vocabulario'], {})

    def test_real_http_handler_roundtrip(self):
        server = backend.ThreadingHTTPServer(('127.0.0.1', 0), backend.RequestHandler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            payload = json.dumps(dict(id='listening_http', word='HTTP test sentence.',
                                      status='desconhecido', pos='LISTENING',
                                      definition_en='HTTP test sentence.',
                                      example_1='HTTP test sentence.')).encode()
            request = urllib.request.Request(
                f'http://127.0.0.1:{server.server_port}/api/evaluate',
                data=payload, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(json.load(response)['success'])
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
