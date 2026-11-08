import sys, pytest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_fixture import make
from src.data import load_recipes
from src.index import RecipeIndex
from src.chat import Bot


@pytest.fixture(scope="session")
def ix(tmp_path_factory):
    d = tmp_path_factory.mktemp("data"); make(d)
    return RecipeIndex(load_recipes(d))


@pytest.fixture
def bot(ix):
    return Bot(ix, use_llm=False)
