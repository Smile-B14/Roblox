from pathlib import Path

p = Path('99 Nights Helper Godmode')
s = p.read_text(encoding='utf-8')

def once(old, new, label):
    global s
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 match, got {count}')
    s = s.replace(old, new, 1)

once(
'''    local baseline = getDiamondCount()
    if baseline == nil then
        state.strongholdStatus = "Waiting for diamond count"
        state.strongholdControl = true
        state.strongholdRetryAt = os.clock() + 2
        return false
    end

    if state.diamondScriptStart == nil then
        state.diamondScriptStart = baseline
    end

    state.strongholdBaseline = baseline''',
'''    local currentCount = getDiamondCount()
    -- Preserve one baseline across retries. If the UI updates late after a
    -- successful chest collection, a retry must still compare against the
    -- count captured before this Stronghold cycle began.
    local baseline = state.strongholdBaseline or currentCount
    if baseline == nil then
        state.strongholdStatus = "Waiting for diamond count"
        state.strongholdControl = true
        state.strongholdRetryAt = os.clock() + 2
        return false
    end

    if state.diamondScriptStart == nil then
        state.diamondScriptStart = currentCount or baseline
    end

    if state.strongholdBaseline == nil then
        state.strongholdBaseline = baseline
    end''',
'preserve stronghold baseline')

once(
'''        local countdown = getStrongholdCountdownText()
        state.strongholdCountdown = countdown

        local doorOpen = strongholdDoorOpen()''',
'''        local countdown = getStrongholdCountdownText()
        state.strongholdCountdown = countdown
        if state.diamondScriptStart == nil then
            state.diamondScriptStart = getDiamondCount()
        end

        local doorOpen = strongholdDoorOpen()''',
'capture script-start diamonds when UI appears')

once(
'''            if normalized ~= "00s" and normalized ~= "0s" and normalized ~= "ready" then
                state.strongholdCycleComplete = false
            end''',
'''            if normalized ~= "00s" and normalized ~= "0s" and normalized ~= "ready" then
                state.strongholdCycleComplete = false
                state.strongholdBaseline = nil
            end''',
'clear baseline on next stronghold cycle')

once(
'''                state.strongholdControl = false
                state.strongholdRunning = false
                state.strongholdStatus = "Off"''',
'''                state.strongholdControl = false
                state.strongholdRunning = false
                state.strongholdBaseline = nil
                state.strongholdStatus = "Off"''',
'clear baseline on diamond farm off')

once(
'''        elseif not state.strongholdCycleComplete and strongholdReady() and not state.strongholdRunning then
            runStrongholdCycle()''',
'''        elseif not state.strongholdCycleComplete
            and strongholdReady()
            and not state.strongholdRunning
            and not state.foodServiceRunning
            and not state.childRescueRunning
            and not state.campBuildRunning then
            runStrongholdCycle()''',
'serialize stronghold start')

once(
'''local function runFoodService()
    if not state.autoFarm or state.foodServiceRunning then
        return
    end''',
'''local function runFoodService()
    if not state.autoFarm or state.foodServiceRunning or state.strongholdControl then
        return
    end''',
'food service stronghold guard')

once(
'''local function runChildRescueAttempt()
    if not state.autoFarm
        or state.childRescueRunning''',
'''local function runChildRescueAttempt()
    if not state.autoFarm
        or state.strongholdControl
        or state.childRescueRunning''',
'child rescue stronghold guard')

once(
'''        if not state.autoFarm then
            break
        end
        if typeof(position) == "Vector3" then''',
'''        if not state.autoFarm or state.strongholdControl then
            break
        end
        if typeof(position) == "Vector3" then''',
'missing child discovery stronghold guard')

once(
'''local function storeChildInSack(sack, child)
    if not state.autoFarm or not sack or not sack.Parent or not child or not child.Parent then''',
'''local function storeChildInSack(sack, child)
    if not state.autoFarm or state.strongholdControl or not sack or not sack.Parent or not child or not child.Parent then''',
'child storing stronghold guard')

once(
'''    local function refreshOpen()
        content.Visible = open
        button.Text = (open and "  ▼  " or "  ▶  ") .. titleText
    end''',
'''    local function refreshOpen()
        content.Visible = open
        content.Size = UDim2.new(1, 0, 0, 0)
        content.AutomaticSize = open and Enum.AutomaticSize.Y or Enum.AutomaticSize.None
        button.Text = (open and "  ▼  " or "  ▶  ") .. titleText
    end''',
'collapsible section sizing')

required = [
    'local baseline = state.strongholdBaseline or currentCount',
    'state.diamondScriptStart = getDiamondCount()',
    'state.strongholdBaseline = nil',
    'or state.strongholdControl then\n        return',
    'content.AutomaticSize = open and Enum.AutomaticSize.Y or Enum.AutomaticSize.None',
]
for needle in required:
    if needle not in s:
        raise RuntimeError(f'missing expected hotfix: {needle!r}')

p.write_text(s, encoding='utf-8')
print('hotfixed')
