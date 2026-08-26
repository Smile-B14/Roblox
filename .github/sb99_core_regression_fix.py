from pathlib import Path
import re

TARGET = Path('99 Nights Helper Godmode')
s = TARGET.read_text(encoding='utf-8')


def once(old, new, label):
    global s
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 match, got {count}')
    s = s.replace(old, new, 1)


def regex_once(pattern, replacement, label):
    global s
    s2, count = re.subn(pattern, replacement, s, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 match, got {count}')
    s = s2


# ---------------------------------------------------------------------------
# State: isolate Stronghold ownership and maintain a monotonic tree-hit token.
# ---------------------------------------------------------------------------
once(
'''    strongholdRetryAt = 0,
    strongholdManualKillRestore = nil,

    range = 200,
    maxInflight = 72,
    inflight = 0,
    targetCooldown = 0.025,
    workerDelay = 0.005,
    combatScanInterval = 0.05,
    capturedTokens = {},''',
'''    strongholdRetryAt = 0,
    strongholdManualKillRestore = nil,
    strongholdAttemptActive = false,

    range = 200,
    maxInflight = 72,
    inflight = 0,
    targetCooldown = 0.06,
    workerDelay = 0.008,
    combatScanInterval = 0.05,
    capturedTokens = {},
    hitSequence = 0,''',
'combat/stronghold state')

once(
'''    campfireTargetLevel = 6,
    campfireMaintainThreshold = 0.80,
    resourcePassLimit = 64,
    resourceServiceRunning = false,''',
'''    campfireTargetLevel = 6,
    campfireMaintainThreshold = 0.80,
    resourcePassLimit = 64,
    resourcePickupRange = 320,
    resourceServiceRunning = false,''',
'resource pickup range')

# ---------------------------------------------------------------------------
# Drag transport: current game expects StopDraggingItem(item), not an empty
# call. Give ownership/teleport replication enough time and always release the
# local drag lock even if an item disappears mid-request.
# ---------------------------------------------------------------------------
regex_once(
r'''local function dragItemTo\(item, destination\).*?\nend\n\nlocal function getFoodCandidates\(\)''',
r'''local function dragItemTo(item, destination)
    if not item or not item.Parent or not state.active then
        return false
    end

    if not isLive(StartDragging) or not isLive(StopDragging) then
        refreshRemotes()
        if not isLive(StartDragging) or not isLive(StopDragging) then
            return false
        end
    end

    if not acquireDragLock(0.75) then
        return false
    end

    local startRemote = StartDragging
    local stopRemote = StopDragging
    local stopSent = false

    local function finishDrag()
        if stopSent then
            return
        end
        stopSent = true
        if isLive(stopRemote) and item and item.Parent then
            callUtilityRemote(stopRemote, 1, item)
        end
    end

    local ok, moved = pcall(function()
        local startedOk, startedResponse = callUtilityRemote(startRemote, 1, item)
        if not startedOk or startedResponse == false then
            return false
        end

        -- Let the server grant drag ownership before changing the item CFrame.
        task.wait(0.08)
        if not item.Parent then
            return false
        end

        local moveOk = pcall(function()
            if item:IsA("Model") then
                item:PivotTo(destination)
            elseif item:IsA("BasePart") then
                item.CFrame = destination
            else
                error("unsupported draggable instance")
            end
        end)
        if not moveOk then
            return false
        end

        -- Current public game implementations leave a replication window and
        -- send the dragged item back to StopDraggingItem explicitly.
        task.wait(0.12)
        finishDrag()
        return item.Parent ~= nil
    end)

    finishDrag()
    dragBusy = false
    return ok and moved == true
end

local function getFoodCandidates()''',
'authoritative drag transport')

# ---------------------------------------------------------------------------
# Combat: tree hit IDs are per-hit in current working implementations. Reusing
# one static prefix can be rejected. Preserve the known/captured suffix but
# advance the prefix, and send the target/trunk CFrame rather than our root CF.
# Also recover the best axe synchronously if the background cache is stale.
# ---------------------------------------------------------------------------
regex_once(
r'''local function makeHitId\(weapon\).*?\nend\n\nlocal attackCooldown''',
r'''local function makeHitId(weapon, isTree)
    local token = state.capturedTokens[weapon.Name] or KNOWN_TOKENS[weapon.Name]
    if not isTree then
        return token or ("1_" .. tostring(weapon:GetAttribute("Owner") or player.UserId))
    end

    state.hitSequence = (tonumber(state.hitSequence) or 0) + 1
    if state.hitSequence > 1000000000 then
        state.hitSequence = 1
    end

    local suffix = type(token) == "string" and string.match(token, "^[^_]+_(.+)$") or nil
    if suffix == nil or suffix == "" then
        suffix = tostring(weapon:GetAttribute("Owner") or player.UserId)
    end
    return tostring(state.hitSequence) .. "_" .. suffix
end

local attackCooldown''',
'fresh combat hit IDs')

once(
'''    local root = getRoot()
    local weapon = bestAxe
    if not root or not root.Parent or not weapon or not weapon.Parent then
        return
    end''',
'''    local root = getRoot()
    local weapon = bestAxe
    if not weapon or not weapon.Parent then
        weapon = select(1, findBestOwned(axeScore))
        bestAxe = weapon
    end
    if not root or not root.Parent or not weapon or not weapon.Parent then
        return
    end''',
'synchronous axe recovery')

once('    local hitId = makeHitId(weapon)', '    local hitId = makeHitId(weapon, isTree)', 'tree-aware hit ID')

once(
'''    local remote = ToolDamageObject
    local attackCFrame = root.CFrame''',
'''    local remote = ToolDamageObject
    local targetPart = nil
    if isTree then
        local trunk = target:FindFirstChild("Trunk", true)
        if trunk and trunk:IsA("BasePart") then
            targetPart = trunk
        end
    end
    targetPart = targetPart or getPart(target)
    local attackCFrame = targetPart and targetPart.CFrame or root.CFrame''',
'target attack CFrame')

# ---------------------------------------------------------------------------
# Smart resources: do not let arbitrary Workspace.Items order waste each pass
# on far-away scrap. Campfire fuel is priority because RequestBurnItem is
# authoritative; scrap/logs are sorted by player distance and collected as the
# Y=30 patrol actually reaches that part of the map.
# ---------------------------------------------------------------------------
regex_once(
r'''local function runResourceService\(\).*?\nend\n\nlocal promptOriginals''',
r'''local function runResourceService()
    if not state.active
        or not state.smartResources
        or state.resourceServiceRunning
        or state.foodServiceRunning
        or state.childRescueRunning
        or state.strongholdControl then
        return
    end

    state.resourceServiceRunning = true
    local serviceOk = pcall(function()
        local level = getCampfireLevel()
        local campfireMaxed = level ~= nil and level >= state.campfireTargetLevel
        local fuelRatio = getCampfireFuelRatio()
        local now = os.clock()

        if campfireMaxed
            and state.autoFarm
            and state.autoChildRescue
            and not state.childRescueCompleted
            and state.childRescueAttempts < state.childRescueMaxAttempts
            and now >= state.nextChildRescueAt then
            state.childRescuePending = true
            cancelFarmTween()
        end

        local items = workspace:FindFirstChild("Items")
        if not items then
            return
        end

        local root = getRoot()
        local candidates = {}
        for _, item in ipairs(items:GetChildren()) do
            if item.Parent == items and (not resourceCooldown[item] or resourceCooldown[item] <= now) then
                local target = resourceTarget(item, campfireMaxed, fuelRatio)
                if target then
                    local part = getPart(item)
                    local distance = math.huge
                    if root and part then
                        distance = (part.Position - root.Position).Magnitude
                    end
                    table.insert(candidates, {
                        item = item,
                        target = target,
                        distance = distance,
                        firePriority = target == CAMPFIRE_DROP,
                    })
                end
            end
        end

        table.sort(candidates, function(a, b)
            if a.firePriority ~= b.firePriority then
                return a.firePriority
            end
            return a.distance < b.distance
        end)

        local processed = 0
        for _, candidate in ipairs(candidates) do
            if not state.active or not state.smartResources or state.strongholdControl then
                break
            end

            local item = candidate.item
            local target = candidate.target
            if item and item.Parent == items then
                -- Remote burning does not require dragging the object through
                -- the map. Scrap/log routing is proximity-aware so nearby drops
                -- from the current patrol tree cannot be starved by far items.
                if target ~= CAMPFIRE_DROP and candidate.distance > state.resourcePickupRange then
                    continue
                end

                resourceCooldown[item] = os.clock() + 0.8
                local handled = false
                if target == CAMPFIRE_DROP then
                    handled = burnItemIntoCampfire(item)
                    if not handled and item.Parent == items and candidate.distance <= state.resourcePickupRange then
                        handled = dragItemTo(item, CFrame.new(CAMPFIRE_DROP))
                    end
                else
                    handled = dragItemTo(item, CFrame.new(target))
                end

                if handled then
                    processed = processed + 1
                    if target == CAMPFIRE_DROP then
                        task.wait(0.08)
                        local updatedLevel = getCampfireLevel()
                        if updatedLevel ~= nil and updatedLevel >= state.campfireTargetLevel then
                            campfireMaxed = true
                        end
                        fuelRatio = getCampfireFuelRatio()
                    else
                        task.wait(0.03)
                    end
                end
            end

            if processed >= state.resourcePassLimit then
                break
            end
        end
    end)

    state.resourceServiceRunning = false
    if not serviceOk then
        -- Retry quickly after a transient streamed-instance race.
        task.wait(0.05)
    end
end

local promptOriginals''',
'nearest smart resource service')

# ---------------------------------------------------------------------------
# Stronghold ownership: FinalGate is a completion signal, never a start signal.
# Missing diamond UI must never seize movement. Only a legitimately-started
# cycle is allowed to retain strongholdControl across retries.
# ---------------------------------------------------------------------------
once(
'''    strongholdManualKillRestore = nil,
    strongholdAttemptActive = false,''',
'''    strongholdManualKillRestore = nil,
    strongholdAttemptActive = false,''',
'stronghold attempt state sanity')

regex_once(
r'''local function strongholdReady\(\).*?\nend\n\nlocal function releaseFarmForStronghold''',
r'''local function strongholdReady()
    local countdown = getStrongholdCountdownText()
    local normalized = string.lower(string.gsub(countdown, "%s+", ""))
    if normalized == "00s" or normalized == "0s" or normalized == "ready" then
        return true
    end

    -- EntryDoors.DoorOpen is a live run/start signal. FinalGate is only used
    -- later to detect completion and must never start Diamond Farm by itself.
    return strongholdDoorOpen()
end

local function releaseFarmForStronghold''',
'stronghold start isolation')

once(
'''    if success then
        state.strongholdControl = false
        state.strongholdCycleComplete = true
        state.strongholdRetryAt = 0''',
'''    if success then
        state.strongholdControl = false
        state.strongholdAttemptActive = false
        state.strongholdCycleComplete = true
        state.strongholdRetryAt = 0''',
'clear successful stronghold attempt')

once(
'''    else
        -- Never release Auto Farm to its under-map/night controller until a
        -- real diamond-count increase has been observed.
        state.strongholdControl = state.diamondFarm
        state.strongholdRetryAt = os.clock() + 3
    end''',
'''    else
        -- Once a real Stronghold run began, retain movement ownership until
        -- the diamond count is verified. Waiting/preflight states never set
        -- strongholdAttemptActive and therefore cannot freeze normal Auto Farm.
        state.strongholdControl = state.diamondFarm and state.strongholdAttemptActive
        state.strongholdRetryAt = os.clock() + 3
    end''',
'failed stronghold ownership')

once(
'''    if baseline == nil then
        state.strongholdStatus = "Waiting for diamond count"
        state.strongholdControl = true
        state.strongholdRetryAt = os.clock() + 2
        return false
    end''',
'''    if baseline == nil then
        state.strongholdStatus = "Waiting for diamond count"
        state.strongholdControl = false
        state.strongholdAttemptActive = false
        state.strongholdRetryAt = os.clock() + 2
        return false
    end''',
'missing diamond count must not seize movement')

once(
'''    if state.strongholdBaseline == nil then
        state.strongholdBaseline = baseline
    end
    state.strongholdControl = true
    state.strongholdRunning = true''',
'''    if state.strongholdBaseline == nil then
        state.strongholdBaseline = baseline
    end
    state.strongholdAttemptActive = true
    state.strongholdControl = true
    state.strongholdRunning = true''',
'arm legitimate stronghold attempt')

once(
'''                state.strongholdCycleComplete = false
                state.strongholdBaseline = nil''',
'''                state.strongholdCycleComplete = false
                state.strongholdBaseline = nil
                state.strongholdAttemptActive = false''',
'reset stronghold attempt with cycle')

once(
'''                state.strongholdControl = false
                state.strongholdRunning = false
                state.strongholdBaseline = nil
                state.strongholdStatus = "Off"''',
'''                state.strongholdControl = false
                state.strongholdRunning = false
                state.strongholdBaseline = nil
                state.strongholdAttemptActive = false
                state.strongholdStatus = "Off"''',
'clear stronghold attempt on disable')

once(
'''        elseif state.strongholdControl and not state.strongholdRunning and os.clock() >= state.strongholdRetryAt then''',
'''        elseif state.strongholdAttemptActive
            and state.strongholdControl
            and not state.strongholdRunning
            and os.clock() >= state.strongholdRetryAt then''',
'retry only real stronghold attempts')

# Manual Diamond toggle reset must also clear the ownership latch.
once(
'''    state.strongholdBaseline = nil
    state.strongholdRetryAt = 0
    state.strongholdCycleComplete = false''',
'''    state.strongholdBaseline = nil
    state.strongholdAttemptActive = false
    state.strongholdRetryAt = 0
    state.strongholdCycleComplete = false''',
'UI stronghold reset')

# ---------------------------------------------------------------------------
# Small, useful live status: expose whether the core has an axe/tree cache and
# whether Smart Resources is active without adding a debug/info page.
# ---------------------------------------------------------------------------
once(
'''        status.Text = string.format(
            "Fire %s/6  |  Farm %dst  |  %s\\nDiamonds %s",
            fireLevel and tostring(fireLevel) or "?",
            radius,
            tostring(state.strongholdStatus or "Off"),
            diamonds and tostring(diamonds) or "--"
        )''',
'''        local axeName = bestAxe and bestAxe.Parent and bestAxe.Name or "none"
        status.Text = string.format(
            "Fire %s/6 | Axe %s | Trees %d\\nSmart %s | SH %s | Diamonds %s",
            fireLevel and tostring(fireLevel) or "?",
            axeName,
            #treeCache,
            state.smartResources and "ON" or "OFF",
            tostring(state.strongholdStatus or "Off"),
            diamonds and tostring(diamonds) or "--"
        )''',
'core status')

required = [
    'callUtilityRemote(stopRemote, 1, item)',
    'local function makeHitId(weapon, isTree)',
    'state.hitSequence = (tonumber(state.hitSequence) or 0) + 1',
    'local attackCFrame = targetPart and targetPart.CFrame or root.CFrame',
    'resourcePickupRange = 320',
    'table.sort(candidates, function(a, b)',
    'return strongholdDoorOpen()',
    'state.strongholdAttemptActive = true',
    'state.strongholdControl = false\n        state.strongholdAttemptActive = false\n        state.strongholdRetryAt',
    'Smart %s | SH %s | Diamonds %s',
]
for needle in required:
    if needle not in s:
        raise RuntimeError(f'missing expected repair: {needle!r}')

for forbidden in [
    'callUtilityRemote(stopRemote, 1)\n',
    'return strongholdDoorOpen() or strongholdGateOpen()',
    'state.strongholdStatus = "Waiting for diamond count"\n        state.strongholdControl = true',
]:
    if forbidden in s:
        raise RuntimeError(f'stale regression remains: {forbidden!r}')

TARGET.write_text(s, encoding='utf-8')
print('core regression repair applied')
