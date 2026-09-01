from __future__ import annotations

import unittest

from context.spec import build_squad
from fast_engine.engine import (
    BurstMachine,
    EventKind,
    EventScheduler,
    compile_burst_policy,
    compile_moris_squad,
)


class BurstMachineTests(unittest.TestCase):
    def _case(self, names, config=None):
        moris = build_squad(names)
        compiled = compile_moris_squad(moris)
        policy = compile_burst_policy(moris, compiled, config)
        scheduler = EventScheduler()
        machine = BurstMachine(compiled, policy)
        machine.start(scheduler)
        return moris, compiled, policy, scheduler, machine

    def test_first_cycle_uses_continuous_time_moris_stage_delays(self):
        _, compiled, _, q, machine = self._case(["리타", "크라운", "홍련", "앨리스", "나가"])
        rows = []
        while q and q.peek_time() <= 13.4 + 1e-8:
            event = q.pop()
            signals = machine.handle(event, q)
            cast = next((s for s in signals if s.event_key == "burst_cast"), None)
            rows.append((event.kind, event.time, None if cast is None else compiled.names[cast.source_actor]))
        self.assertEqual([row[0] for row in rows], [
            EventKind.BURST_READY,
            EventKind.BURST_ACTIVATE,
            EventKind.BURST_ACTIVATE,
            EventKind.BURST_ACTIVATE,
            EventKind.FULL_BURST_START,
            EventKind.FULL_BURST_END,
            EventKind.BURST_END_FINALIZE,
        ])
        expected_times = [3.0, 3.05, 3.20, 3.35, 3.40, 13.40, 13.40]
        for row, expected in zip(rows, expected_times):
            self.assertAlmostEqual(row[1], expected, places=9)
        self.assertEqual([r[2] for r in rows[1:4]], ["리타", "크라운", "홍련"])

    def test_full_burst_end_keeps_cast_flags_until_same_time_finalize(self):
        _, compiled, _, q, machine = self._case(["리타", "크라운", "홍련", "앨리스", "나가"])
        end_event = None
        end_signals = ()
        while q:
            event = q.pop()
            signals = machine.handle(event, q)
            if event.kind is EventKind.FULL_BURST_END:
                end_event = event
                end_signals = signals
                break

        self.assertIsNotNone(end_event)
        self.assertTrue(all(signal.event_key == "full_burst_end" for signal in end_signals))
        casted_names = {
            compiled.names[actor]
            for actor, casted in enumerate(machine.casted)
            if casted
        }
        self.assertEqual(casted_names, {"리타", "크라운", "홍련"})

        finalize = q.pop()
        self.assertEqual(finalize.kind, EventKind.BURST_END_FINALIZE)
        self.assertAlmostEqual(finalize.time, end_event.time, places=9)
        self.assertEqual(machine.handle(finalize, q), ())
        self.assertFalse(any(machine.casted))

        # The ordinary next-cycle token must remain current; the finalize event
        # deliberately does not participate in generation invalidation.
        next_ready = q.pop()
        self.assertEqual(next_ready.kind, EventKind.BURST_READY)
        self.assertGreater(next_ready.time, finalize.time)
        self.assertTrue(machine.handle(next_ready, q))

    def test_moris_burst_pattern_is_compiled_without_character_specific_runtime_logic(self):
        names = ["리타", "크라운", "마스트 : 로망틱 메이드", "홍련", "앨리스"]
        _, compiled, policy, q, machine = self._case(names)
        maid_actor = compiled.names.index("마스트 : 로망틱 메이드")
        self.assertIn(maid_actor, policy.patterns)
        self.assertEqual(policy.patterns[maid_actor].every, 3)

        b2 = []
        while q and len(b2) < 4:
            event = q.pop()
            for signal in machine.handle(event, q):
                if signal.event_key == "squad_burst_cast:2":
                    b2.append(compiled.names[signal.source_actor])
        self.assertEqual(b2, ["크라운", "크라운", "마스트 : 로망틱 메이드", "크라운"])

    def test_burst_signals_are_owner_scoped_for_trigger_index(self):
        _, compiled, _, q, machine = self._case(["리타", "크라운", "홍련", "앨리스", "나가"])
        event = q.pop()
        signals = machine.handle(event, q)
        self.assertEqual({s.owner_actor for s in signals}, set(range(5)))
        self.assertTrue(all(s.event_key == "burst_enter:1" for s in signals))
        # Runtime dispatcher can now query only the owner bucket instead of filtering all effects.
        for signal in signals:
            compiled.trigger_index.for_actor_event(signal.owner_actor, signal.event_key)

    def test_cooldown_reduction_reschedules_wait_and_stale_event_becomes_noop(self):
        _, compiled, _, q, machine = self._case(["리타", "크라운", "홍련", "앨리스", "나가"])
        # Run first cycle and the next gauge-ready event. B1 리타 is still on its 20 s CD,
        # so the machine schedules a wait until 23.05 in the approximation baseline.
        while q and machine.cycle_count < 1:
            machine.handle(q.pop(), q)
        ready = q.pop()
        self.assertEqual(ready.kind, EventKind.BURST_END_FINALIZE)
        machine.handle(ready, q)
        ready = q.pop()
        self.assertEqual(ready.kind, EventKind.BURST_READY)
        machine.handle(ready, q)
        activation = q.pop()
        self.assertEqual(activation.kind, EventKind.BURST_ACTIVATE)
        machine.handle(activation, q)
        old_wait_time = q.peek_time()
        self.assertIsNotNone(old_wait_time)
        self.assertGreater(old_wait_time, activation.time)

        # The old wait remains in the heap. A cooldown reduction schedules an earlier
        # generation; heap deletion is unnecessary because the old token becomes stale.
        rita = compiled.names.index("리타")
        machine.reduce_cooldown(rita, 10.0, activation.time, q)
        new_wait = q.pop()
        self.assertLess(new_wait.time, old_wait_time)
        self.assertTrue(machine.handle(new_wait, q))
        while q and q.peek_time() < old_wait_time - 1e-9:
            machine.handle(q.pop(), q)
        stale = q.pop()
        self.assertAlmostEqual(stale.time, old_wait_time)
        self.assertEqual(machine.handle(stale, q), ())


if __name__ == "__main__":
    unittest.main()
