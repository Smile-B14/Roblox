from pathlib import Path
import re

TARGET = Path('99 Nights Helper Godmode')
s = TARGET.read_text(encoding='utf-8')


def replace_once(old, new, label):
    global s
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 match, got {count}')
    s = s.replace(old, new, 1)


def regex_once(pattern, replacement, label, flags=re.S):
    global s
    s2, count = re.subn(pattern, replacement, s, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 regex match, got {count}')
    s = s2

# ---------------------------------------------------------------------------
# The live debug report showed 20-70 outstanding ToolDamageObject invokes and
# ~900 generated tree hit IDs in three seconds. Bound combat aggressively so
# the selected patrol tree gets useful server calls instead of remote flooding.
# ---------------------------------------------------------------------------
replace_once(
'''    range = 200,
    maxInflight = 16,
    inflight = 0,
    targetCooldown = 0.08,
    workerDelay = 0.012,
    combatScanInterval = 0.05,
    capturedTokens = {},
    hitSequence = 0,''',
'''    range = 200,
    maxInflight = 8,
    inflight = 0,
    targetCooldown = 0.12,
    workerDelay = 0.02,
    combatScanInterval = 0.08,
    capturedTokens = {},
    hitSequence = 0,
    lastAttackAccepted = 0,
    lastAttackRejected = 0,''',
'combat pressure state')

replace_once(
'''    resourcePassLimit = 12,
    resourcePickupRange = 360,
    resourceServiceRunning = false,''',
'''    resourcePassLimit = 8,
    resourcePickupRange = 220,
    resourcePauseUntil = 0,
    resourceServiceRunning = false,''',
'resource pressure state')

# ---------------------------------------------------------------------------
# Restore the pre-Diamond hit token behavior. The debug build was generating a
# different tree token on every call. The known-good helper used the captured
# legitimate token or the known tool token. Keep hitSequence only as a debug
# counter. Also aim the CFrame at the actual target and track server acceptance.
# ---------------------------------------------------------------------------
regex_once(
r'''local function makeHitId\(weapon, isTree\).*?\nlocal treeCache = \{\}''',
r'''local function makeHitId(weapon)
    return state.capturedTokens[weapon.Name]
        or KNOWN_TOKENS[weapon.Name]
end

local attackCooldown = setmetatable({}, { __mode = "k" })

local function attackTarget(target, isTree)
    if not isLive(ToolDamageObject) then
        refreshRemotes()
        if not isLive(ToolDamageObject) then
            return
        end
    end

    if not target or not target.Parent or state.inflight >= state.maxInflight then
        return
    end

    if not isTree then
        local humanoid = target:FindFirstChildOfClass("Humanoid")
        if humanoid and humanoid.Health <= 0 then
            return
        end
    end

    local root = getRoot()
    local weapon = bestAxe
    if not weapon or not weapon.Parent then
        weapon = select(1, findBestOwned(axeScore))
        bestAxe = weapon
    end
    if not root or not root.Parent or not weapon or not weapon.Parent then
        return
    end

    local now = os.clock()
    local previous = attackCooldown[target]
    if previous and now - previous < state.targetCooldown then
        return
    end

    local hitId = makeHitId(weapon)
    if not hitId then
        return
    end

    attackCooldown[target] = now
    state.hitSequence = (tonumber(state.hitSequence) or 0) + 1
    ensureAxeArmed(weapon)

    local targetPart = nil
    if isTree then
        local trunk = target:FindFirstChild("Trunk", true)
        if trunk and trunk:IsA("BasePart") then
            targetPart = trunk
        end
    end
    targetPart = targetPart or getPart(target)

    local attackCFrame = root.CFrame
    if targetPart then
        local direction = targetPart.Position - root.Position
        if direction.Magnitude > 0.001 then
            local lookOk, lookCF = pcall(CFrame.lookAt, root.Position, targetPart.Position)
            if lookOk then
                attackCFrame = lookCF
            end
        end
    end

    local remote = ToolDamageObject
    if remote:IsA("RemoteEvent") then
        state.inflight = state.inflight + 1
        local ok = pcall(remote.FireServer, remote, target, weapon, hitId, attackCFrame)
        if ok then
            state.lastAttackAccepted = os.clock()
        else
            state.lastAttackRejected = os.clock()
        end
        state.inflight = math.max(0, state.inflight - 1)
        return
    end

    if not remote:IsA("RemoteFunction") then
        return
    end

    state.inflight = state.inflight + 1
    local released = false
    local function releaseInflight()
        if released then return end
        released = true
        state.inflight = math.max(0, state.inflight - 1)
    end

    local attackThread
    attackThread = task.spawn(function()
        local ok, response = pcall(remote.InvokeServer, remote, target, weapon, hitId, attackCFrame)
        if ok and response ~= false then
            state.lastAttackAccepted = os.clock()
        else
            state.lastAttackRejected = os.clock()
        end
        releaseInflight()
    end)

    task.delay(1, function()
        if released then return end
        if type(task.cancel) == "function" and attackThread then
            pcall(task.cancel, attackThread)
        end
        state.lastAttackRejected = os.clock()
        releaseInflight()
    end)
end

local treeCache = {}''',
'pre-diamond combat protocol')

# Limit each scan to nearest targets. Manual aura stays useful, while Auto Farm
# focuses almost entirely on the tree it travelled to.
regex_once(
r'''local cachedEntities = \{\}\nlocal cachedTrees = \{\}\nlocal lastCombatScan = 0\n\ntask\.spawn\(function\(\).*?\nend\)\n\n--==============================================================\n-- NIGHT DETECTION''',
r'''local cachedEntities = {}
local cachedTrees = {}
local lastCombatScan = 0

task.spawn(function()
    while state.active do
        local root = getRoot()

        if root and (state.killAura or state.autoChop) then
            local now = os.clock()
            if now - lastCombatScan >= state.combatScanInterval then
                lastCombatScan = now
                cachedEntities = state.killAura and sortedEntities(root) or {}
                cachedTrees = state.autoChop and sortedTrees(root) or {}
            end

            if state.killAura then
                local budget = state.autoFarm and 3 or 5
                for index = 1, math.min(budget, #cachedEntities) do
                    if state.inflight >= state.maxInflight then break end
                    attackTarget(cachedEntities[index].target, false)
                end
            end

            if state.autoChop then
                local budget = state.autoFarm and 1 or 3
                for index = 1, math.min(budget, #cachedTrees) do
                    if state.inflight >= state.maxInflight then break end
                    attackTarget(cachedTrees[index].target, true)
                end
            end
        else
            cachedEntities = {}
            cachedTrees = {}
        end

        task.wait((state.killAura or state.autoChop) and state.workerDelay or 0.08)
    end
end)

--==============================================================
-- NIGHT DETECTION''',
'bounded nearest combat worker')

# ---------------------------------------------------------------------------
# Lighting.ClockTime is not a reliable phase signal in this game. The report
# showed Day 1 while Auto Farm repeatedly returned to the night platform. Only
# replicated explicit night/phase state may send Auto Farm underground.
# ---------------------------------------------------------------------------
regex_once(
r'''local function isNight\(\).*?\nend\n\n--==============================================================\n-- AUTO FARM MOVEMENT / FOOD SERVICE''',
r'''local function isNight()
    local sources = {}
    local map = workspace:FindFirstChild("Map")
    local campground = map and map:FindFirstChild("Campground")
    table.insert(sources, workspace)
    if map then table.insert(sources, map) end
    if campground then table.insert(sources, campground) end
    table.insert(sources, Lighting)

    local boolNames = {
        "IsNight", "Night", "Nighttime", "IsNightTime", "NightActive", "NightStarted",
    }
    for _, object in ipairs(sources) do
        for _, name in ipairs(boolNames) do
            local ok, value = pcall(object.GetAttribute, object, name)
            if ok then
                if type(value) == "boolean" then
                    return value
                elseif type(value) == "number" and (value == 0 or value == 1) then
                    return value == 1
                elseif type(value) == "string" then
                    local text = string.lower(value)
                    if text == "true" or text == "night" then return true end
                    if text == "false" or text == "day" then return false end
                end
            end
        end
    end

    local phaseNames = { "Phase", "Cycle", "TimeOfDay", "DayNightState", "WorldPhase" }
    for _, object in ipairs(sources) do
        for _, name in ipairs(phaseNames) do
            local ok, value = pcall(object.GetAttribute, object, name)
            if ok and type(value) == "string" then
                local text = string.lower(value)
                if string.find(text, "night", 1, true) then return true end
                if string.find(text, "day", 1, true)
                    or string.find(text, "dawn", 1, true)
                    or string.find(text, "morning", 1, true) then
                    return false
                end
            end
        end
    end

    -- Unknown phase is treated as daytime. The game's custom lighting can use
    -- a nighttime ClockTime while the actual gameplay phase is visibly day.
    return false
end

--==============================================================
-- AUTO FARM MOVEMENT / FOOD SERVICE''',
'explicit-only night detection')

# ---------------------------------------------------------------------------
# Smart resources: use the same physical drag/drop path used by current working
# public scripts. Never call RequestBurnItem after the item may already have
# been consumed. Verify FuelRemaining/level or campground wood/scrap before
# proceeding to another item, preventing the mass "item is no longer in
# workspace" loss shown in the report.
# ---------------------------------------------------------------------------
regex_once(
r'''local resourceCooldown = setmetatable\(\{\}, \{ __mode = "k" \}\).*?\nlocal promptOriginals = G\.SB99_PROMPT_ORIGINALS''',
r'''local resourceCooldown = setmetatable({}, { __mode = "k" })

local function resourceTarget(item, campfireMaxed, fuelRatio)
    if not campfireMaxed then
        return isFuelResource(item) and "fire" or nil
    end

    if isLogResource(item) or isScrapResource(item) then
        return "scrap"
    end

    if isFuelResource(item)
        and fuelRatio ~= nil
        and fuelRatio < state.campfireMaintainThreshold then
        return "fire"
    end
    return nil
end

local function getPhysicalFireDrop()
    local fire = getMainFire()
    local center = fire and fire:FindFirstChild("Center", true)
    if center and center:IsA("BasePart") then
        return center.CFrame * CFrame.new(0, 30, 0), center.Position
    end
    return CFrame.new(CAMPFIRE_DROP + Vector3.new(0, 30, 0)), CAMPFIRE_DROP
end

local function getPhysicalScrapDrop()
    local map = workspace:FindFirstChild("Map")
    local campground = map and map:FindFirstChild("Campground")
    local scrapper = campground and campground:FindFirstChild("Scrapper")
    local dashed = scrapper and scrapper:FindFirstChild("DashedLine", true)
    if dashed and dashed:IsA("BasePart") then
        return dashed.CFrame * CFrame.new(0, 30, 0), dashed.Position
    end
    return CFrame.new(SCRAP_DROP + Vector3.new(0, 30, 0)), SCRAP_DROP
end

local function getCampTotals()
    local map = workspace:FindFirstChild("Map")
    local campground = map and map:FindFirstChild("Campground")
    if not campground then return nil, nil end
    return tonumber(campground:GetAttribute("TotalWood")), tonumber(campground:GetAttribute("TotalScrap"))
end

local function burnItemIntoCampfire(item)
    if not item or not item.Parent then return false end
    local fire = getMainFire()
    if not fire then return false end

    local beforeFuel = tonumber(fire:GetAttribute("FuelRemaining")) or 0
    local beforeLevel = getCampfireLevel() or tonumber(state.fireDerivedLevel) or 1
    local dropCF = getPhysicalFireDrop()
    local moved = dragItemTo(item, dropCF)
    if not moved and item.Parent then
        return false
    end

    local deadline = os.clock() + 2
    repeat
        task.wait(0.10)
        local liveFire = getMainFire()
        if liveFire then
            local afterFuel = tonumber(liveFire:GetAttribute("FuelRemaining")) or 0
            local afterLevel = getCampfireLevel() or beforeLevel
            if afterFuel > beforeFuel + 0.001 or afterLevel > beforeLevel then
                return true
            end
        end
    until not state.active or os.clock() >= deadline

    return false
end

local function routeItemToScrapper(item)
    if not item or not item.Parent then return false end
    local beforeWood, beforeScrap = getCampTotals()
    local dropCF = getPhysicalScrapDrop()
    local moved = dragItemTo(item, dropCF)
    if not moved and item.Parent then
        return false
    end

    local deadline = os.clock() + 1.8
    repeat
        task.wait(0.10)
        local wood, scrap = getCampTotals()
        if beforeWood ~= nil and wood ~= nil and wood > beforeWood then
            return true
        end
        if beforeScrap ~= nil and scrap ~= nil and scrap > beforeScrap then
            return true
        end
    until not state.active or os.clock() >= deadline

    return false
end

local function runResourceService()
    local now = os.clock()
    if not state.active
        or not state.smartResources
        or state.resourceServiceRunning
        or state.foodServiceRunning
        or state.childRescueRunning
        or state.strongholdControl
        or now < (tonumber(state.resourcePauseUntil) or 0) then
        return
    end

    state.resourceServiceRunning = true
    pcall(function()
        local level = getCampfireLevel() or tonumber(state.fireDerivedLevel) or 1
        local campfireMaxed = level >= state.campfireTargetLevel
        local fuelRatio = getCampfireFuelRatio()

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
        local root = getRoot()
        if not items or not root then return end

        local candidates = {}
        for _, item in ipairs(items:GetChildren()) do
            if item.Parent == items and (not resourceCooldown[item] or resourceCooldown[item] <= now) then
                local target = resourceTarget(item, campfireMaxed, fuelRatio)
                if target then
                    local part = getPart(item)
                    if part then
                        local distance = (part.Position - root.Position).Magnitude
                        if distance <= state.resourcePickupRange then
                            table.insert(candidates, {
                                item = item,
                                target = target,
                                distance = distance,
                            })
                        end
                    end
                end
            end
        end

        table.sort(candidates, function(a, b)
            if a.target ~= b.target then
                return a.target == "fire"
            end
            return a.distance < b.distance
        end)

        local processed = 0
        for _, candidate in ipairs(candidates) do
            if not state.active or not state.smartResources or state.strongholdControl then break end
            local item = candidate.item
            if item and item.Parent == items then
                resourceCooldown[item] = os.clock() + 1
                local handled = candidate.target == "fire"
                    and burnItemIntoCampfire(item)
                    or routeItemToScrapper(item)

                if not handled then
                    resourceCooldown[item] = os.clock() + 3
                    state.resourcePauseUntil = os.clock() + 0.8
                    break
                end

                processed = processed + 1
                if candidate.target == "fire" then
                    level = getCampfireLevel() or level
                    campfireMaxed = level >= state.campfireTargetLevel
                    fuelRatio = getCampfireFuelRatio()
                end
                task.wait(0.05)
            end

            if processed >= state.resourcePassLimit then break end
        end
    end)
    state.resourceServiceRunning = false
end

local promptOriginals = G.SB99_PROMPT_ORIGINALS''',
'verified physical resource routing')

# Auto Farm already descends to trunk height after the first debug-guided pass.
# Shorten the dwell now that combat is focused and rate-limited.
replace_once(
'''                            local chopDeadline = os.clock() + 3
                            repeat
                                attackTarget(tree, true)
                                task.wait(0.09)''',
'''                            local chopDeadline = os.clock() + 1.6
                            repeat
                                attackTarget(tree, true)
                                task.wait(0.12)''',
'focused tree dwell')

# Status remains compact but exposes whether the combat queue is staying bounded.
if 'Inflight %d' not in s:
    raise RuntimeError('expected diagnostic inflight status from previous repair')

TARGET.write_text(s, encoding='utf-8')
