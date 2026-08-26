from pathlib import Path

TARGET = Path("99 Nights Helper Godmode")
EXPECTED_BLOB = "f8ce3d614c6d61049fe3b937a2a828ac85aa3b98"
s = TARGET.read_text(encoding="utf-8")


def replace_once(old: str, new: str):
    global s
    count = s.count(old)
    if count != 1:
        raise SystemExit(f"expected one anchor, found {count}: {old[:100]!r}")
    s = s.replace(old, new, 1)


def replace_between(start: str, end: str, new_middle: str):
    global s
    i = s.find(start)
    if i < 0:
        raise SystemExit(f"missing start marker: {start!r}")
    j = s.find(end, i + len(start))
    if j < 0:
        raise SystemExit(f"missing end marker: {end!r}")
    s = s[:i] + new_middle + s[j:]


# ---------- state / feature ownership ----------
replace_once(
'''    autoChildRescue = false,\n    diamondFarm = false,\n''',
'''    autoChildRescue = false,\n    diamondFarm = false,\n    fullbright = true,\n''')

replace_once(
'''    range = 200,\n    maxInflight = 8,\n    inflight = 0,\n    targetCooldown = 0.12,\n    workerDelay = 0.02,\n    combatScanInterval = 0.08,\n    capturedTokens = {},\n    hitSequence = 0,\n    lastAttackAccepted = 0,\n    lastAttackRejected = 0,\n''',
'''    range = 200,\n    maxInflight = 12,\n    maxTreeInflight = 5,\n    maxEntityInflight = 7,\n    inflight = 0,\n    treeInflight = 0,\n    entityInflight = 0,\n    targetCooldown = 0.10,\n    workerDelay = 0.02,\n    combatScanInterval = 0.08,\n    capturedTokens = {},\n    hitSequence = 0,\n    lastAttackAccepted = 0,\n    lastAttackRejected = 0,\n    focusTree = nil,\n    lastCombatError = nil,\n    lastResourceError = nil,\n    lastFarmError = nil,\n''')

replace_once(
'''    treeServiceEvery = 4,\n    treeHoldSeconds = 1.6,\n    treeApproachSpeed = 90,\n''',
'''    treeServiceEvery = 4,\n    treeHoldSeconds = 2.2,\n    treeApproachSpeed = 90,\n''')

replace_once(
'''    resourcePassLimit = 48,\n''',
'''    resourcePassLimit = 32,\n''')

# ---------- default Fullbright + No Fog, kept independent of gameplay phase ----------
visual_anchor = '''G.SB99_FIRE_DERIVED_LEVEL = nil\nG.SB99_FIRE_LAST_TARGET = nil\n\n'''
if s.count(visual_anchor) != 1:
    raise SystemExit("visual insertion anchor missing/duplicated")
visual_block = r'''G.SB99_FIRE_DERIVED_LEVEL = nil
G.SB99_FIRE_LAST_TARGET = nil

-- Default visual assistance. This deliberately does NOT change ClockTime, so
-- Fullbright cannot interfere with the game's replicated day/night phase.
if type(G.SB99_LIGHTING_ORIGINAL) ~= "table" then
    G.SB99_LIGHTING_ORIGINAL = {
        Brightness = Lighting.Brightness,
        Ambient = Lighting.Ambient,
        OutdoorAmbient = Lighting.OutdoorAmbient,
        FogStart = Lighting.FogStart,
        FogEnd = Lighting.FogEnd,
        FogColor = Lighting.FogColor,
        GlobalShadows = Lighting.GlobalShadows,
        ExposureCompensation = Lighting.ExposureCompensation,
    }
end
if type(G.SB99_ATMOSPHERE_ORIGINALS) ~= "table" then
    G.SB99_ATMOSPHERE_ORIGINALS = setmetatable({}, { __mode = "k" })
end
local atmosphereOriginals = G.SB99_ATMOSPHERE_ORIGINALS

local function rememberAtmosphere(atmosphere)
    if not atmosphere or not atmosphere:IsA("Atmosphere") or atmosphereOriginals[atmosphere] then
        return
    end
    atmosphereOriginals[atmosphere] = {
        Density = atmosphere.Density,
        Haze = atmosphere.Haze,
        Glare = atmosphere.Glare,
    }
end

local function applyFullbright()
    if not state.active or not state.fullbright then
        return
    end
    pcall(function()
        Lighting.Brightness = math.max(Lighting.Brightness, 3)
        Lighting.Ambient = Color3.new(1, 1, 1)
        Lighting.OutdoorAmbient = Color3.new(1, 1, 1)
        Lighting.GlobalShadows = false
        Lighting.ExposureCompensation = math.max(Lighting.ExposureCompensation, 0.35)
        Lighting.FogStart = 0
        Lighting.FogEnd = 1000000000
    end)
    for _, child in ipairs(Lighting:GetChildren()) do
        if child:IsA("Atmosphere") then
            rememberAtmosphere(child)
            pcall(function()
                child.Density = 0
                child.Haze = 0
                child.Glare = 0
            end)
        end
    end
end

local function restoreFullbright()
    local original = G.SB99_LIGHTING_ORIGINAL
    if type(original) == "table" then
        pcall(function()
            Lighting.Brightness = original.Brightness
            Lighting.Ambient = original.Ambient
            Lighting.OutdoorAmbient = original.OutdoorAmbient
            Lighting.FogStart = original.FogStart
            Lighting.FogEnd = original.FogEnd
            Lighting.FogColor = original.FogColor
            Lighting.GlobalShadows = original.GlobalShadows
            Lighting.ExposureCompensation = original.ExposureCompensation
        end)
    end
    for atmosphere, originalAtmosphere in pairs(atmosphereOriginals) do
        if atmosphere and atmosphere.Parent and type(originalAtmosphere) == "table" then
            pcall(function()
                atmosphere.Density = originalAtmosphere.Density
                atmosphere.Haze = originalAtmosphere.Haze
                atmosphere.Glare = originalAtmosphere.Glare
            end)
        end
    end
end

state.applyFullbright = applyFullbright
state.restoreFullbright = restoreFullbright
applyFullbright()
track(Lighting.ChildAdded:Connect(function(child)
    if child:IsA("Atmosphere") then
        rememberAtmosphere(child)
        if state.fullbright then
            task.defer(applyFullbright)
        end
    end
end))
task.spawn(function()
    while state.active do
        if state.fullbright then
            pcall(applyFullbright)
        end
        task.wait(0.5)
    end
end)

'''
s = s.replace(visual_anchor, visual_block, 1)

# ---------- combat: tree calls get their own budget and can never be starved by Kill Aura ----------
replace_once(
'''local function makeHitId(weapon)\n    return state.capturedTokens[weapon.Name]\n        or KNOWN_TOKENS[weapon.Name]\nend\n''',
'''local function makeHitId(weapon)\n    -- Keep the known/captured IDs, but retain the universal fallback used by\n    -- the pre-Diamond build and current public 99 Nights aura implementations.\n    return state.capturedTokens[weapon.Name]\n        or KNOWN_TOKENS[weapon.Name]\n        or 999\nend\n''')

attack_start = 'local function attackTarget(target, isTree)\n'
attack_end = 'local treeCache = {}\n'
new_attack = r'''local function attackTarget(target, isTree)
    if not isLive(ToolDamageObject) then
        refreshRemotes()
        if not isLive(ToolDamageObject) then
            return false
        end
    end

    if not target or not target.Parent then
        return false
    end

    local typeInflight = isTree and state.treeInflight or state.entityInflight
    local typeLimit = isTree and state.maxTreeInflight or state.maxEntityInflight
    if state.inflight >= state.maxInflight or typeInflight >= typeLimit then
        return false
    end

    if not isTree then
        local humanoid = target:FindFirstChildOfClass("Humanoid")
        if humanoid and humanoid.Health <= 0 then
            return false
        end
    end

    local root = getRoot()
    local weapon = bestAxe
    if not weapon or not weapon.Parent then
        weapon = select(1, findBestOwned(axeScore))
        bestAxe = weapon
    end
    if not root or not root.Parent or not weapon or not weapon.Parent then
        return false
    end

    local now = os.clock()
    local previous = attackCooldown[target]
    if previous and now - previous < state.targetCooldown then
        return false
    end

    local hitId = makeHitId(weapon)
    attackCooldown[target] = now
    state.hitSequence = (tonumber(state.hitSequence) or 0) + 1
    ensureAxeArmed(weapon)

    -- The pre-Diamond helper and current working aura implementations use the
    -- player's current root CFrame for ToolDamageObject. Do not synthesize a
    -- lookAt CFrame here; some server builds reject that shape for tree hits.
    local attackCFrame = root.CFrame
    local remote = ToolDamageObject

    local released = false
    local function reserveInflight()
        state.inflight = state.inflight + 1
        if isTree then
            state.treeInflight = state.treeInflight + 1
        else
            state.entityInflight = state.entityInflight + 1
        end
    end
    local function releaseInflight()
        if released then return end
        released = true
        state.inflight = math.max(0, state.inflight - 1)
        if isTree then
            state.treeInflight = math.max(0, state.treeInflight - 1)
        else
            state.entityInflight = math.max(0, state.entityInflight - 1)
        end
    end

    if remote:IsA("RemoteEvent") then
        reserveInflight()
        local ok = pcall(remote.FireServer, remote, target, weapon, hitId, attackCFrame)
        if ok then
            state.lastAttackAccepted = os.clock()
        else
            state.lastAttackRejected = os.clock()
        end
        releaseInflight()
        return ok
    end

    if not remote:IsA("RemoteFunction") then
        return false
    end

    reserveInflight()
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

    task.delay(1.25, function()
        if released then return end
        if type(task.cancel) == "function" and attackThread then
            pcall(task.cancel, attackThread)
        end
        state.lastAttackRejected = os.clock()
        releaseInflight()
    end)
    return true
end

'''
replace_between(attack_start, attack_end, new_attack)

worker_start = 'local cachedEntities = {}\nlocal cachedTrees = {}\nlocal lastCombatScan = 0\n\ntask.spawn(function()\n'
night_header = '--==============================================================\n-- NIGHT DETECTION\n'
new_worker = r'''local cachedEntities = {}
local cachedTrees = {}
local lastCombatScan = 0

task.spawn(function()
    while state.active do
        local ok, err = pcall(function()
            local root = getRoot()
            if root and (state.killAura or state.autoChop) then
                local now = os.clock()
                if now - lastCombatScan >= state.combatScanInterval then
                    lastCombatScan = now
                    cachedEntities = state.killAura and sortedEntities(root) or {}
                    cachedTrees = state.autoChop and sortedTrees(root) or {}
                end

                -- Trees go first. Auto Farm used to process Kill Aura first,
                -- letting slow enemy RemoteFunctions fill the shared pool and
                -- starve every tree hit.
                if state.autoChop then
                    local budget = state.autoFarm and 2 or 3
                    if state.focusTree and state.focusTree.Parent then
                        attackTarget(state.focusTree, true)
                    end
                    for index = 1, math.min(budget, #cachedTrees) do
                        if state.treeInflight >= state.maxTreeInflight then break end
                        local target = cachedTrees[index].target
                        if target ~= state.focusTree then
                            attackTarget(target, true)
                        end
                    end
                end

                if state.killAura then
                    local budget = state.autoFarm and (state.focusTree and 1 or 3) or 5
                    for index = 1, math.min(budget, #cachedEntities) do
                        if state.entityInflight >= state.maxEntityInflight then break end
                        attackTarget(cachedEntities[index].target, false)
                    end
                end
            else
                cachedEntities = {}
                cachedTrees = {}
            end
            state.lastCombatTick = os.clock()
        end)

        if not ok then
            state.lastCombatError = tostring(err)
            cachedEntities = {}
            cachedTrees = {}
            task.wait(0.1)
        else
            task.wait((state.killAura or state.autoChop) and state.workerDelay or 0.08)
        end
    end
end)

'''
replace_between(worker_start, night_header, new_worker)

# ---------- stronger campfire level observation ----------
level_start = 'local function getCampfireLevel()\n'
ratio_start = 'local function getCampfireFuelRatio()\n'
new_level = r'''local function parseCampfireLevelText(text)
    if type(text) ~= "string" then return nil end
    local lower = string.lower(text)
    local number = string.match(lower, "campfire%s*level%s*([1-6])")
        or string.match(lower, "fire%s*level%s*([1-6])")
        or string.match(lower, "level%s*([1-6])")
    number = tonumber(number)
    if number and number >= 1 and number <= state.campfireTargetLevel then
        return number
    end
    return nil
end

local function rememberFireLevel(level)
    level = tonumber(level)
    if not level then return nil end
    level = math.clamp(math.floor(level + 0.001), 1, state.campfireTargetLevel)
    state.fireDerivedLevel = level
    G.SB99_FIRE_DERIVED_LEVEL = level
    return level
end

local function getCampfireLevel()
    local progress = tonumber(workspace:GetAttribute("Progress"))
    if progress == nil then
        local progressObject = workspace:FindFirstChild("Progress")
        if progressObject then
            local ok, value = pcall(function() return progressObject.Value end)
            if ok then progress = tonumber(value) end
        end
    end
    if progress ~= nil then
        return rememberFireLevel(progress)
    end

    local fire = getMainFire()
    if not fire then
        return tonumber(state.fireDerivedLevel)
    end
    local campground = fire.Parent

    local level = readNumberValue(fire, {
        "Progress", "CampfireProgress", "Level", "FireLevel", "CampfireLevel", "UpgradeLevel", "CurrentLevel",
    })
    if level == nil and campground then
        level = readNumberValue(campground, {
            "Progress", "CampfireProgress", "CampfireLevel", "FireLevel", "CurrentFireLevel", "MainFireLevel",
        })
    end
    if level == nil then
        level = readNumberValue(workspace, {
            "Progress", "CampfireProgress", "CampfireLevel", "FireLevel", "CurrentFireLevel", "MainFireLevel",
        })
    end
    if level ~= nil then
        return rememberFireLevel(level)
    end

    -- Some builds expose the level only through a SurfaceGui/BillboardGui.
    for _, object in ipairs(fire:GetDescendants()) do
        if object:IsA("TextLabel") or object:IsA("TextButton") then
            local ok, text = pcall(function() return object.Text end)
            local parsed = ok and parseCampfireLevelText(text) or nil
            if parsed then return rememberFireLevel(parsed) end
        end
    end

    -- Player UI scan is throttled because Interface can contain many objects.
    local now = os.clock()
    if now >= (tonumber(state.nextFireGuiScan) or 0) then
        state.nextFireGuiScan = now + 1
        local interface = playerGui:FindFirstChild("Interface")
        local found = nil
        if interface then
            for _, object in ipairs(interface:GetDescendants()) do
                if object:IsA("TextLabel") or object:IsA("TextButton") then
                    local ancestor = object.Parent
                    local related = false
                    for _ = 1, 5 do
                        if not ancestor then break end
                        local name = string.lower(ancestor.Name)
                        if string.find(name, "campfire", 1, true) or string.find(name, "fire", 1, true) then
                            related = true
                            break
                        end
                        ancestor = ancestor.Parent
                    end
                    if related then
                        local ok, text = pcall(function() return object.Text end)
                        local parsed = ok and parseCampfireLevelText(text) or nil
                        if parsed then
                            found = parsed
                            break
                        end
                    end
                end
            end
        end
        state.fireGuiLevel = found
    end
    if state.fireGuiLevel then
        return rememberFireLevel(state.fireGuiLevel)
    end

    -- Final fallback: observe FuelTarget changes continuously. This is kept
    -- session-local and cannot inherit a fake level from an earlier execution.
    local target = tonumber(fire:GetAttribute("FuelTarget"))
    if target ~= nil and target > 0 then
        local previousTarget = tonumber(state.fireLastTarget)
        if previousTarget == nil then
            state.fireLastTarget = target
        elseif math.abs(target - previousTarget) > 0.001 then
            state.fireDerivedLevel = math.clamp(
                (tonumber(state.fireDerivedLevel) or 1) + 1,
                1,
                state.campfireTargetLevel
            )
            state.fireLastTarget = target
        end
        G.SB99_FIRE_DERIVED_LEVEL = state.fireDerivedLevel
        G.SB99_FIRE_LAST_TARGET = state.fireLastTarget
    end

    return tonumber(state.fireDerivedLevel) or 1
end

'''
replace_between(level_start, ratio_start, new_level)

# ---------- fuel/resource classification ----------
replace_once(
'''local function isLogResource(item)\n    local name = lowerName(item)\n    return name == "log"\n        or string.find(name, " log", 1, true) ~= nil\n        or string.find(name, "log ", 1, true) ~= nil\nend\n''',
'''local function isLogResource(item)\n    local name = lowerName(item)\n    -- Wet Logs are intentionally excluded: current game weather can create\n    -- them, but they are not valid normal campfire fuel.\n    if string.find(name, "wet log", 1, true) then\n        return false\n    end\n    return name == "log"\n        or string.find(name, " log", 1, true) ~= nil\n        or string.find(name, "log ", 1, true) ~= nil\nend\n''')

replace_once(
'''    if FUEL_NAMES[name] or isLogResource(item) then\n        return true\n    end\n\n    local fuel = tonumber(item:GetAttribute("FuelAmount"))\n''',
'''    if FUEL_NAMES[name] or isLogResource(item) then\n        return true\n    end\n    -- Entity corpses are also legitimate campfire fuel in current builds.\n    if string.find(name, "corpse", 1, true) then\n        return true\n    end\n\n    local fuel = tonumber(item:GetAttribute("FuelAmount"))\n''')

replace_once(
'''    if isFuelResource(item)\n        and fuelRatio ~= nil\n        and fuelRatio < state.campfireMaintainThreshold then\n        return "fire"\n    end\n''',
'''    if isFuelResource(item)\n        and (fuelRatio == nil or fuelRatio < state.campfireMaintainThreshold) then\n        return "fire"\n    end\n''')

# Exact receiver coordinates requested by the user; never float items 30 studs above them.
fire_drop_start = 'local function getPhysicalFireDrop()\n'
get_totals_start = 'local function getCampTotals()\n'
new_drops = r'''local function getPhysicalFireDrop()
    return CFrame.new(CAMPFIRE_DROP), CAMPFIRE_DROP
end

local function getPhysicalScrapDrop()
    return CFrame.new(SCRAP_DROP), SCRAP_DROP
end

'''
replace_between(fire_drop_start, get_totals_start, new_drops)

# Fast resource-only drag uses the same global lock as food/gear so systems cannot
# fight over ownership, but it has shorter replication windows than general item handling.
insert_after_totals = '''local function getCampTotals()\n    local map = workspace:FindFirstChild("Map")\n    local campground = map and map:FindFirstChild("Campground")\n    if not campground then return nil, nil end\n    return tonumber(campground:GetAttribute("TotalWood")), tonumber(campground:GetAttribute("TotalScrap"))\nend\n\n'''
if s.count(insert_after_totals) != 1:
    raise SystemExit("getCampTotals insertion anchor missing")
fast_drop = r'''local function getCampTotals()
    local map = workspace:FindFirstChild("Map")
    local campground = map and map:FindFirstChild("Campground")
    if not campground then return nil, nil end
    return tonumber(campground:GetAttribute("TotalWood")), tonumber(campground:GetAttribute("TotalScrap"))
end

local function fastResourceDrop(item, destination)
    if not item or not item.Parent or not state.active then return false end
    if not isLive(StartDragging) or not isLive(StopDragging) then
        refreshRemotes()
    end
    if not isLive(StartDragging) or not isLive(StopDragging) then return false end
    if not acquireDragLock(1.5) then return false end

    local startRemote = StartDragging
    local stopRemote = StopDragging
    local stopSent = false
    local function stopDrag()
        if stopSent then return end
        stopSent = true
        if item and item.Parent and isLive(stopRemote) then
            if stopRemote:IsA("RemoteEvent") then
                pcall(stopRemote.FireServer, stopRemote, item)
            else
                callUtilityRemote(stopRemote, 0.75, item)
            end
        end
    end

    local ok, moved = pcall(function()
        local started = false
        if startRemote:IsA("RemoteEvent") then
            started = pcall(startRemote.FireServer, startRemote, item)
        else
            local requestOk, response = callUtilityRemote(startRemote, 0.75, item)
            started = requestOk and response ~= false
        end
        if not started then return false end

        task.wait(0.10)
        if not item.Parent then return true end
        local moveOk = pcall(function()
            if item:IsA("Model") then
                item:PivotTo(destination)
            elseif item:IsA("BasePart") then
                item.CFrame = destination
            else
                error("unsupported draggable resource")
            end
        end)
        if not moveOk then return false end
        task.wait(0.15)
        stopDrag()
        task.wait(0.03)
        return true
    end)

    stopDrag()
    dragBusy = false
    return ok and moved == true
end

'''
s = s.replace(insert_after_totals, fast_drop, 1)

burn_start = 'local function burnItemIntoCampfire(item)\n'
resource_start = 'local function runResourceService()\n'
new_burn_route = r'''local function burnItemIntoCampfire(item)
    if not item or not item.Parent then return false end
    if not getMainFire() then return false end

    local dropCF = CFrame.new(CAMPFIRE_DROP)
    local moved = fastResourceDrop(item, dropCF)
    if not moved and item.Parent then
        moved = dragItemTo(item, dropCF)
    end

    -- The game normally burns physical fuel when it is released in the fire.
    -- RequestBurnItem is only a best-effort nudge AFTER the physical drop, so a
    -- remote signature change cannot make Smart Resources depend on it.
    if item.Parent and isLive(RequestBurnItem) then
        local fire = getMainFire()
        if fire then
            if RequestBurnItem:IsA("RemoteEvent") then
                pcall(RequestBurnItem.FireServer, RequestBurnItem, fire, item)
            elseif RequestBurnItem:IsA("RemoteFunction") then
                task.spawn(function()
                    callUtilityRemote(RequestBurnItem, 0.75, fire, item)
                end)
            end
        end
    end

    task.wait(0.10)
    getCampfireLevel()
    return moved or not item.Parent
end

local function routeItemToScrapper(item)
    if not item or not item.Parent then return false end
    local dropCF = CFrame.new(SCRAP_DROP)
    local moved = fastResourceDrop(item, dropCF)
    if not moved and item.Parent then
        moved = dragItemTo(item, dropCF)
    end
    return moved or not item.Parent
end

'''
replace_between(burn_start, resource_start, new_burn_route)

prompt_start = 'local promptOriginals = G.SB99_PROMPT_ORIGINALS\n'
new_resource = r'''local function runResourceService()
    local now = os.clock()
    if not state.active
        or not state.smartResources
        or state.resourceServiceRunning
        or state.foodServiceRunning
        or state.childRescueRunning
        or state.campBuildRunning
        or state.strongholdControl
        or now < (tonumber(state.resourcePauseUntil) or 0) then
        return
    end

    state.resourceServiceRunning = true
    local serviceOk, serviceErr = pcall(function()
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
                    local distance = part and (part.Position - root.Position).Magnitude or math.huge
                    if target == "fire" or (part and distance <= state.resourcePickupRange) then
                        table.insert(candidates, { item = item, target = target, distance = distance })
                    end
                end
            end
        end

        table.sort(candidates, function(a, b)
            if a.target ~= b.target then return a.target == "fire" end
            if a.target == "fire" then
                local ap, bp = fuelPriority(a.item), fuelPriority(b.item)
                if ap ~= bp then return ap > bp end
            end
            return a.distance < b.distance
        end)

        local processed = 0
        for _, candidate in ipairs(candidates) do
            if not state.active or not state.smartResources or state.strongholdControl then break end
            local item = candidate.item
            if item and item.Parent == items then
                -- Always recalculate from live fire state. If Level 6 is reached
                -- during this same pass, the very next Log switches to Scrapper.
                level = getCampfireLevel() or level
                campfireMaxed = level >= state.campfireTargetLevel
                fuelRatio = getCampfireFuelRatio()
                local liveTarget = resourceTarget(item, campfireMaxed, fuelRatio)

                if liveTarget then
                    local handled = liveTarget == "fire"
                        and burnItemIntoCampfire(item)
                        or routeItemToScrapper(item)
                    resourceCooldown[item] = os.clock() + (handled and 1.25 or 0.75)
                    if handled then processed = processed + 1 end
                    task.wait(0.03)
                end
            end
            if processed >= state.resourcePassLimit then break end
        end
    end)

    if not serviceOk then
        state.lastResourceError = tostring(serviceErr)
    end
    state.resourceServiceRunning = false
end

'''
replace_between(resource_start, prompt_start, new_resource)

# Resource supervisor should retry promptly after short ownership races.
replace_once(
'''        if state.smartResources then\n            runResourceService()\n            task.wait(0.35)\n''',
'''        if state.smartResources then\n            pcall(runResourceService)\n            task.wait(0.25)\n''')

# ---------- Auto Farm controller: focus tree gets explicit priority, loop self-heals ----------
farm_controller_start = '-- Main Auto Farm controller.\ntask.spawn(function()\n'
ui_defer_start = 'task.defer(function()\n--==============================================================\n-- PHONE-FIRST COLLAPSIBLE UI\n'
new_farm_controller = r'''-- Main Auto Farm controller. Every iteration is protected so one stale streamed
-- tree/part cannot permanently kill the Auto Farm task.
task.spawn(function()
    local wasNight = false

    while state.active do
        local iterationOk, iterationErr = pcall(function()
            if not state.autoFarm then
                state.focusTree = nil
                wasNight = false
                task.wait(0.4)
                return
            end

            if state.strongholdControl then
                state.focusTree = nil
                state.releaseFarmForStronghold()
                wasNight = false
                task.wait(0.25)
                return
            end

            local night = isNight()
            if night then
                state.focusTree = nil
                if not wasNight then cancelFarmTween() end
                local character = getCharacter()
                local root = getRoot()
                if character and (not root or (root.Position - FARM_HOME).Magnitude > 1.5) then
                    pcall(character.PivotTo, character, CFrame.new(FARM_HOME))
                end
                lockFarmCharacter()
                wasNight = true
                if state.emergencyFoodRun or foodServiceDue() then runFoodService() end
                task.wait(0.5)
                return
            end

            wasNight = false
            if state.childRescuePending and not state.childRescueRunning then
                state.focusTree = nil
                runChildRescueAttempt()
                task.wait(0.2)
            elseif state.emergencyFoodRun or foodServiceDue() then
                state.focusTree = nil
                moveFarmTo(getFarmCenter(), true)
                runFoodService()
                task.wait(0.2)
            else
                local point, tree = nextDayFarmTarget()
                if point and moveFarmTo(point, false) then
                    if tree and tree.Parent and state.autoChop then
                        state.focusTree = tree
                        attackCooldown[tree] = nil
                        bestAxe = select(1, findBestOwned(axeScore)) or bestAxe
                        if bestAxe and bestAxe.Parent then
                            ensureAxeArmed(bestAxe)
                        end

                        local treePart = tree:FindFirstChild("Trunk", true)
                        if not (treePart and treePart:IsA("BasePart")) then
                            treePart = getPart(tree)
                        end
                        if treePart and treePart.Parent then
                            moveFarmTo(Vector3.new(
                                treePart.Position.X,
                                treePart.Position.Y + 4,
                                treePart.Position.Z
                            ), false, state.treeApproachSpeed)
                        end

                        local holdUntil = os.clock() + (tonumber(state.treeHoldSeconds) or 2.2)
                        repeat
                            if tree and tree.Parent and smallTreeAvailable(tree) then
                                attackTarget(tree, true)
                            end
                            task.wait(0.10)
                        until not state.autoFarm
                            or state.strongholdControl
                            or isNight()
                            or not smallTreeAvailable(tree)
                            or os.clock() >= holdUntil

                        state.focusTree = nil
                        if state.autoFarm and not state.strongholdControl and not isNight() then
                            local liveRoot = getRoot()
                            if liveRoot then
                                moveFarmTo(Vector3.new(
                                    liveRoot.Position.X,
                                    FARM_PATROL_Y,
                                    liveRoot.Position.Z
                                ), false, state.treeApproachSpeed)
                            end
                        end
                    else
                        state.focusTree = nil
                        task.wait(0.12)
                    end
                else
                    state.focusTree = nil
                    task.wait(0.1)
                end
            end
            state.lastFarmTick = os.clock()
        end)

        if not iterationOk then
            state.lastFarmError = tostring(iterationErr)
            state.focusTree = nil
            cancelFarmTween()
            task.wait(0.15)
        end
    end
end)

'''
replace_between(farm_controller_start, ui_defer_start, new_farm_controller)

# Reset focus on farm enable/disable.
replace_once(
'''    state.patrolIndex = 0\n    state.patrolExploreIndex = 0\n    state.resourcePauseUntil = 0\n''',
'''    state.patrolIndex = 0\n    state.patrolExploreIndex = 0\n    state.focusTree = nil\n    state.resourcePauseUntil = 0\n''')
replace_once(
'''    state.autoFarm = false\n    state.emergencyFoodRun = false\n''',
'''    state.autoFarm = false\n    state.focusTree = nil\n    state.emergencyFoodRun = false\n''')

# ---------- UI toggle + more useful compact status ----------
ui_anchor = '''makeToggle(farmSection, "Auto Farm - full suite", function() return state.autoFarm end, function(v)\n    if v then enableFarm() else disableFarm() end\nend, false)\n'''
if s.count(ui_anchor) != 1:
    raise SystemExit("UI farm toggle anchor missing")
s = s.replace(ui_anchor, ui_anchor + r'''makeToggle(farmSection, "Fullbright + No Fog", function() return state.fullbright end, function(v)
    state.fullbright = v
    if v then
        state.applyFullbright()
    else
        state.restoreFullbright()
    end
end, false)
''', 1)

replace_once(
'''            "Fire %s/6 | Axe %s | Trees %d | Inflight %d\\nSmart %s | SH %s | Diamonds %s",\n            fireLevel and tostring(fireLevel) or "?",\n            axeName,\n            #treeCache,\n            state.inflight,\n            state.smartResources and "ON" or "OFF",\n            tostring(state.strongholdStatus or "Off"),\n            diamonds and tostring(diamonds) or "--"\n''',
'''            "Fire %s/6 | Axe %s | Trees %d | Hit T%d/E%d\\nSmart %s | Light %s | Diamonds %s",\n            fireLevel and tostring(fireLevel) or "?",\n            axeName,\n            #treeCache,\n            state.treeInflight,\n            state.entityInflight,\n            state.smartResources and "ON" or "OFF",\n            state.fullbright and "ON" or "OFF",\n            diamonds and tostring(diamonds) or "--"\n''')

# Static safety assertions for this revision.
required = [
    'maxTreeInflight = 5',
    'maxEntityInflight = 7',
    'or 999',
    'state.focusTree = tree',
    'CFrame.new(CAMPFIRE_DROP)',
    'CFrame.new(SCRAP_DROP)',
    'local function fastResourceDrop',
    'state.fullbright = v',
    'Lighting.FogEnd = 1000000000',
    'state.campBuildRunning',
]
for needle in required:
    if needle not in s:
        raise SystemExit(f"required feature missing after patch: {needle}")

if 'center.CFrame * CFrame.new(0, 30, 0)' in s:
    raise SystemExit('old +30 fire drop survived')
if 'dashed.CFrame * CFrame.new(0, 30, 0)' in s:
    raise SystemExit('old +30 scrap drop survived')

TARGET.write_text(s, encoding="utf-8")
print("patched", len(s), "bytes")
