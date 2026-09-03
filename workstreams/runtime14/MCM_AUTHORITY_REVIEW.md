# MCM interaction-origin review - approval-dependent work

Status: both relay defects reproduced; no changed UI interaction is approved or
implemented. The pending question now covers a dedicated MCM tab containing both
the master checkbox and body-choice selector, not merely the master control.
The old sender-free event relay is NOT accepted; its tests remain mandatory RED.

## Exact local primary source trace

Paths below are relative to
`C:/Claude Projects/BG3 Mods/ChatGPT Work Files/Research Sources/BG3-MCM/Mod Configuration Menu/Mods/BG3MCM/ScriptExtender/Lua/`.

- `Server/MCMServer.lua:85`: `SetSettingValue` emits modUUID, settingId, value and
  oldValue through MCM_SETTING_SAVED with bothContexts=true; no original sender.
- `Shared/Helpers/Events/ModEventManager.lua:60`: emitModEvent broadcasts the
  event to client contexts, and throws the same data locally. A receiving host
  client is not evidence that the original interaction belonged to the host.
- `Client/Components/IMGUIWidgets/CheckboxIMGUIWidget.lua:14`: the actual local
  checkbox OnChange calls IMGUIAPI:SetSettingValue. The label OnClick also calls
  that setter. `UpdateCurrentValue` only assigns Checked. These are distinct
  interaction and display-update paths; shared saved events are not clicks.
- `Client/IMGUIAPI.lua:228` and `:240`: findWidgetForSetting and GetModWidgets are
  explicitly private, with a warning about lost stored references. Intercepting
  those generated widgets is not a supported public integration contract.
- `Shared/Helpers/MCM/GlobalTable/MCMAPIImplementations.lua:473`: the public
  EventButton.RegisterCallback implementation is client-only and delegates to
  the event-button callback registry. It is a supported candidate, but replacing
  a checkbox with separate buttons changes the product interaction.
- Same file `:635` and `:676`: public InsertModMenuTab accepts a tab name and
  creation callback, mod UUID and skipDisclaimer flag. A Runtime-owned local
  checkbox/selector can use its own interaction callbacks and existing
  server-validated request channel; a new tab changes the control layout.
- `Client/IMGUIAPI.lua:38`: InsertModMenuTab deduplicates by callback identity
  before calling MCMProxy. Use a stable callback, not a newly allocated callback
  on each event or reload.
- `Client/MCMProxy.lua:68-112`: insertion initializes its game-state subject,
  defers through two ticks, and waits for UIReady; in Running it inserts the tab,
  while menu behavior uses a disclaimer unless skipDisclaimer is selected.
  Runtime must use this public lifecycle, not poll or intercept private widgets.

No historical MCM minimum version or installed-build compatibility is inferred
from this source snapshot. Required public API presence must be feature-checked
and source/test coverage supplied for the eventual approved implementation.

## Production reproductions

`test_r1_review_round1.lua`, selector `mcm`, executes the actual server/client
bootstraps with engine-only fixtures:

1. A multiplayer sender-free master event is denied on the server. Its relay
   through the actual host client becomes a host-authenticated network request
   and changes MasterEnabled. The originating guest interaction was lost.
2. One guest body-choice broadcast is delivered to host and guest clients. Each
   resolves its own controlled character at forwarding time. Both resulting
   requests pass target ownership checks, and the host character changes without
   any host interaction. Target authorization does not authenticate intent.

Both cases are RED (0/2) against the committed checkpoint. The host fixture uses
the actual reserved user 1 and corresponding peer 1; guest uses its distinct
reserved user and peer normalization. Earlier setup attempts omitted multiplayer
enumeration or used a guest peer for the host relay; those did not reproduce the
claimed two-context defect and are not accepted evidence.

## Requirements for the approved solution

- Preserve one-click operation if the checkbox/selector tab is selected; only
  local UI callbacks may send mutation intent. Guest master requests are still
  rejected by authoritative server ownership checks. Client host labels are not
  authority, and rebroadcast payloads cannot trigger mutations.
- Read initial/current controls from server-authoritative per-save/per-character
  state. Rejections and failure/partial states must refresh the display. Programmatic
  display updates must not create saved-event or request write loops.
- Resolve the currently controlled target at interaction time; never capture a
  stale character in tab-construction callbacks. Rebuild/load/switch-save and
  unavailable-target cases need tests, as do duplicate subscription prevention.
- Remove or replace the old generated clickable controls once their approved
  replacement is functional. Leaving a nonfunctional or misleading master/body
  setting beside the new control is not an acceptable fix. Metadata/storage and
  server feedback for legacy setting IDs must be explicitly reconciled.
- Keep Off/External timing unchanged; the separate pending-refresh decision is
  not authorization for a UI redesign or vice versa.
