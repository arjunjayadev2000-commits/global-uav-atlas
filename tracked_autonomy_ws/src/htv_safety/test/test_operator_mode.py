from htv_safety.operator_mode import OperatorMode, OperatorModeStateMachine
from htv_safety.state_machine import SafetyState


def test_starts_manual_and_never_enables_itself():
    op = OperatorModeStateMachine()
    for t in range(100):
        op.update(float(t), SafetyState.READY, True)
    assert op.mode == OperatorMode.MANUAL
    assert not op.operator_enable


def test_enable_arms_then_follows_supervisor():
    op = OperatorModeStateMachine()
    ok, _ = op.request_enable(0.0, SafetyState.READY, True)
    assert ok and op.mode == OperatorMode.AUTONOMY_ARMED and op.enable_sequence == 1
    op.update(0.1, SafetyState.AUTONOMOUS, False)
    assert op.mode == OperatorMode.AUTONOMOUS


def test_enable_refused_in_latched_or_unknown_state():
    op = OperatorModeStateMachine()
    assert not op.request_enable(0.0, SafetyState.EMERGENCY_STOP, True)[0]
    assert not op.request_enable(0.0, None, True)[0]
    assert op.mode == OperatorMode.MANUAL


def test_supervisor_stop_drops_to_stopped_then_manual():
    op = OperatorModeStateMachine()
    op.request_enable(0.0, SafetyState.READY, True)
    op.update(0.1, SafetyState.AUTONOMOUS, False)
    op.update(0.2, SafetyState.CONTROLLED_STOP, False)
    assert op.mode == OperatorMode.STOPPED and not op.operator_enable
    op.update(0.3, SafetyState.STANDBY, True)
    assert op.mode == OperatorMode.MANUAL


def test_disable_and_arm_timeout():
    op = OperatorModeStateMachine(arm_timeout=1.0)
    op.request_enable(0.0, SafetyState.READY, True)
    op.update(2.0, SafetyState.READY, True)
    assert op.mode == OperatorMode.STOPPED
    op.update(2.1, SafetyState.READY, True)
    op.request_enable(3.0, SafetyState.READY, True)
    assert op.request_disable()[0]
    assert op.mode == OperatorMode.STOPPED
    assert op.enable_sequence == 2
