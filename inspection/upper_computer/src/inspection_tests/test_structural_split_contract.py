from pathlib import Path


def test_fsm_runtime_services_are_split_into_ingress_egress_and_metrics_modules() -> None:
    root = Path(__file__).resolve().parents[2]
    fsm_node = (root / 'src' / 'inspection_fsm' / 'inspection_fsm' / 'fsm_node.py').read_text(encoding='utf-8')
    ingress = (root / 'src' / 'inspection_fsm' / 'inspection_fsm' / 'fsm_ingress.py').read_text(encoding='utf-8')
    egress = (root / 'src' / 'inspection_fsm' / 'inspection_fsm' / 'fsm_egress.py').read_text(encoding='utf-8')
    metrics = (root / 'src' / 'inspection_fsm' / 'inspection_fsm' / 'fsm_metrics.py').read_text(encoding='utf-8')
    assert 'from .fsm_ingress import FsmIngressAdapter' in fsm_node
    assert 'from .fsm_egress import FsmEgressPublisher' in fsm_node
    assert 'from .fsm_metrics import FsmMetricsService' in fsm_node
    assert 'class FsmIngressAdapter' in ingress
    assert 'class FsmEgressPublisher' in egress
    assert 'class FsmMetricsService' in metrics


def test_gateway_recipe_store_delegates_to_split_components() -> None:
    root = Path(__file__).resolve().parents[2]
    recipe_store = (root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'recipe_store.py').read_text(encoding='utf-8')
    recipe_components = (root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'recipe_components.py').read_text(encoding='utf-8')
    assert 'RecipeRepository' in recipe_store
    assert 'RecipeActivationService' in recipe_store
    assert 'RecipeRevisionArchive' in recipe_store
    assert 'class RecipeRepository' in recipe_components
    assert 'class RecipeActivationService' in recipe_components
    assert 'class RecipeRevisionArchive' in recipe_components


def test_gateway_auth_service_delegates_to_split_components() -> None:
    root = Path(__file__).resolve().parents[2]
    auth = (root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'auth.py').read_text(encoding='utf-8')
    components = (root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'auth_components.py').read_text(encoding='utf-8')
    assert 'CredentialStore' in auth
    assert 'SessionService' in auth
    assert 'WsTicketService' in auth
    assert 'class CredentialStore' in components
    assert 'class SessionService' in components
    assert 'class WsTicketService' in components
