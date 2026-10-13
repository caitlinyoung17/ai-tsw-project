import pytest

from utils import exceptions as ex

TREE = [
    (ex.ConfigError, ex.TswError), (ex.WorkflowFilesNotFound, ex.TswError),
    (ex.WorkflowFormatError, ex.TswError), (ex.EmptyDocumentError, ex.TswError),
    (ex.LLMError, ex.TswError), (ex.LLMResponseError, ex.LLMError),
    (ex.PayloadValidationError, ex.LLMError), (ex.LLMTransientError, ex.LLMError),
    (ex.BatchError, ex.LLMError), (ex.UnknownModelError, ex.TswError),
    (ex.VocabularyError, ex.TswError), (ex.VocabularyLoadError, ex.VocabularyError),
    (ex.VocabularyFormatError, ex.VocabularyError),
    (ex.VocabHttpError, ex.VocabularyError), (ex.VocabParseError, ex.VocabularyError),
    (ex.StepFailedError, ex.TswError),
]


@pytest.mark.parametrize("child,parent", TREE)
def test_hierarchy(child, parent):
    assert issubclass(child, parent)


def test_attributes():
    cause = ValueError("x")
    e = ex.WorkflowFormatError("bad", path="/a/b", cause=cause)
    assert str(e) == "bad" and e.path == "/a/b" and e.cause is cause
    assert e.__cause__ is cause


def test_defaults_and_step():
    e = ex.TswError("m")
    assert e.path is None and e.cause is None
    assert ex.StepFailedError("m", step="s1").step == "s1"
