# Inventory-preserving refresh investigation

## Dirty overlay note (2026-09-03, not a Task 2 acceptance)

Wait-then-apply is implemented on the current dirty overlay: in-flight
RefreshEquipment is completed before Off/External; delayed re-equip still
refuses after the gate; wait >= ~2s shows player-visible `Please Wait for Body Morph`.
Stateful `test_r1_pending_refresh.lua` is Wait PASS (4/4 + WAIT_NOTIFY) on this
tree. This is not an exclusion and not Task 2 acceptance. MCM origin-proof remains
OPEN. Historical RED reproduction below is retained as prior-head evidence.

Status (historical, prior heads): no verified replacement had been established and
the stateful suite was RED. That present-tense RED does not describe this dirty tree.

## Reproduced conflict

The real managed `EquipRace.RefreshEquipment` / family refresh first call
`Osi.Unequip`, then schedule `Osi.Equip` for a later callback. An immediate
External transition closes the gate; the required delayed-callback guard then
suppresses re-equip. The stateful engine fixture records the item in inventory
but no longer in its equipped slot. Therefore zero gated calls alone was not
proof that equipped-item identity/state was preserved.

Immediate master-off, no External equipment writes, and item-state preservation
remain mandatory. Delaying/rejecting Off, completing an equip while External, or
removing managed refresh is not implemented or authorized by this investigation.

## Primary local sources inspected

1. `ChatGPT Work Files/Research Sources/bg3se/Docs/API.md`, lines 873-883:
   `Entity:Replicate(component)` marks a component for replication. It does not
   document forced EquipmentRace visual-map re-evaluation.
2. Same repository, `BG3Extender/Lua/Shared/Proxies/LuaEntityProxy.inl`, lines
   356-387: `ReplicateComponent` sets replication bits, dirties the replication
   buffer, and refuses unmapped/non-replicable components or non-server context.
   `Replicate` sets all bits in word zero. There is no equipment-render refresh
   operation in that implementation.
3. Same repository, `GameDefinitions/Components/Components.h`, lines 203-209:
   `EquipmentVisualComponent` exposes a single `State` byte. Its semantics are
   not documented there; assigning a guessed value is not a supported mechanism.
4. Same repository, `GameDefinitions/Components/Visual.h`, lines 963 onward:
   client equipment visual systems expose request/state collections. The local
   release notes say `Ext.System` and these systems were added in v25, and later
   visual systems in v30. Those are not a verified SE20-floor substitute.
5. `Research Sources/CCEE/ScriptExtender/Lua/_Libs/FocusCore/Shared/Helpers/Appearance.lua`
   (read completely), lines 36-55: character appearance changes replicate
   GameObjectVisual and EquipmentVisual, with a GameObjectVisual event changing
   the root-template visual. This is inventory-preserving code, but it is not
   evidence that unchanged template identity plus a changed EquipmentRace causes
   all equipped visual arrays to re-resolve. CCEE Config requires SE27.
6. `Research Sources/Appearance-Edit-Enhanced/.../Shared/Utils.lua`, complete
   `CopyAppearanceVisuals` function at lines 667-698: updates AppearanceOverride
   and replicates GameObjectVisual/AppearanceOverride. Config requires SE23.
7. `Research Sources/NessusLib/.../Entity/Visual.lua` (read completely):
   `Visual.Replicate` at lines 24-33 replicates CharacterCreationAppearance and
   GameObjectVisual. `BetterAddVisualOverride` at 59-74 copies/appends the CCA
   visual array directly and replication is separate. Config requires SE22.
8. `ClothMorph_Build/05_equipmentrace_probe/PROBE_GUIDE.md` (read completely):
   steps/results at 69 and 160 bind the prior positive EquipmentRace render
   observation to re-equipping. They do not establish replication-only refresh.

The local bg3se source checkout is clean at
`c1c7503d4923c16e324a7bc4ac6103d410315fa7` (2026-07-11), with only the locally
available shallow history and no tags. It cannot establish older SE20 support
from history. `C:/Claude Projects/BG3 Mods/BG3SE_Docs/API.md` is zero bytes; it
provided no additional documentation. The existing R0 package's declared SE20
floor is not itself proof that a newly selected mechanism was available in SE20.
Conversely, the whole-mod SE27/23/22 floors above do not establish that these
particular replication/array operations require those versions: unrelated
features may determine a mod's floor. Existing accepted R0 already uses direct
CCA.Visuals assignment and CCA replication; that is relevant retained-surface
evidence, not a fabricated versioned API minimum.

## Supported conclusions and remaining options

- Replication is a documented inventory-preserving operation, and working mod
  sources use it for visual/appearance changes. Replication-only EquipmentRace
  re-resolution remains an unverified candidate, not an implemented fix.
- Natural equipment re-resolution is allowed by the pass-through design after
  restoration, but these sources do not prove an immediate managed-mode refresh
  from changing EquipmentRace alone.
- Client system request collections/undocumented State values are not an
  acceptable guessed substitute, and newer-system APIs do not meet the pinned
  SE20 floor without a separate approved lineage change.
- A controlled gameplay probe would be needed to establish whether documented
  component replication re-resolves the current equipped mesh arrays while
  preserving item identity, timing, materials, and both normal/camp sets. Such a
  live action is not authorized by the current request.
- The controller has separately requested a user choice about waiting for an
  already-started refresh. No approval was received by this worker and no such
  behavioral change has been implemented.

## Separate CCSV timing finding that blocks acceptance

The original live probe guide at lines 148-151 explicitly records that
`AddCustomVisualOverride` was not visible in the same command tick's visual-list
readback, although the body rendered and a later revert removed it. The current
qualification fixture's former synchronous native append and immediate success
guard did not establish real-engine CCSV acceptance.

A source-backed alternative to investigate is the direct CCA.Visuals append plus
replication used in NessusLib, also using the same direct-array write surface as
ClothMorph's existing removal path. Alternatively a journalled asynchronous
readback would need an exact documented transaction design. The controller
authorized the bounded direct-array correction after the source trace below;
it is now implemented and separately tested. No completed-render or gameplay
claim follows from synchronous array readback.

The production engine fixture now queues native additions separately from Lua
timers by default. `test_r1_native_visual_timing.lua` covers same-command
invisibility, successful managed application without untracked native work,
and an External switch before native work becomes visible. There is no claim
that Runtime's Lua timer gates can cancel already-issued native engine work.

## Direct CCA write support trace

At the exact bg3se checkout above, `Components/Visual.h:100` declares writable
`CharacterCreationAppearanceComponent.Visuals` as `Array<Guid>`.
`LuaPropertyMapHelpers.h:42` routes non-value assignment through the property's
unserializer. `Helpers/LuaUnserialize.h:540` selects array-table conversion and
its lines 18-43 clear/populate the actual Array directly. The older serializer
at `LuaSerializers.h:255` uses the same clear/populate pattern.
`LuaArrayProxy.h:65` also implements indexed array writes/appends directly.
Replication remains the separately documented propagation step, not a guarantee
of completed rendering before it returns. R0 BootstrapServer lines 13-18 and
325-344 already use the same direct-array assignment and CCA replication for
owned removal and record a live revert result. NessusLib's exact addition
function preserves the live entries, appends one, and assigns the array. These
are source-backed grounds to qualify a scoped synchronous CCSV addition using
that retained write surface; they do not resolve equipment visual refresh.

The initial native timing fixture ran RED 1/3; expanded ownership-preservation
and failure cases ran RED 2/8. The corrected source passed 8/8 in freshly verified
stage `ae9ca976c1b84ebc8aaa278a4773dd06`, alongside all then-included production
suites (exact-source pytest 2 passed in 67.57 seconds). Portable tests passed
59 with 5 explicit skips. The stateful pending-refresh fixture was then executed
against that same stage and remained RED. It is now included in the mandatory
exact-source aggregate, so its unresolved requirement prevents aggregate success.

The mandatory combined suite subsequently completed with 1 failed, 480 passed,
15 skipped in 103.73 seconds. Receipt
`6d1ad75869f942a6a16eee20ff10fe3f.evidence.json` binds that run and all syntax
checks; the failure is the stateful pending-refresh case. The fixture has since
been expanded to both EquipRace/BodyFamilyEquipRace and External/master-off:
all four cases reproduce the same inventory failure (0/4), with zero delayed
equipment writes. No refresh behavior was changed.

Final CCA failure-path review also added a one-shot replication rejection after
successful array assignment. It exposes a further RED (8/9 timing cases): the
current candidate returns failure without claiming or retiring the real append.
The recorded server write and later client replication must be distinguished
without fabricating ownership for a rejected assignment or failed readback.
The additional propagation cases were expanded to RED 8/11 before correction.
The controller confirmed that successful server-array assignment with exact
same-CV readback is a proven write; later failed propagation must not erase its
claim. The candidate now records that proof before replication, blocks additional
managed mutation on propagation failure, and uses existing owned restoration.
Direct debug/reconcile callers without an enclosing state transaction use the
existing External journal. Failed rollback retains the claim and partial journal;
verified removal retires it while preserving current unrelated entries.

Final receipt `5df5dd83c5434f88983eaa2c3d4948f1` records timing **11/11**, alongside
all other implemented suites and 21 successful Lua syntax checks. The mandatory
combined run remains RED: **1 failed, 480 passed, 15 skipped in 120.36 seconds**,
solely on the pending-refresh suite **0/4**. Thus the CCA timing/propagation
correction does not resolve or waive the inventory-refresh design conflict.
