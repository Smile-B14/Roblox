from pathlib import Path
import re

TARGET = Path('99 Nights Helper Godmode')
s = TARGET.read_text(encoding='utf-8')


def once(old, new, label):
    global s
    count = s.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 exact match, got {count}')
    s = s.replace(old, new, 1)


def regex_once(pattern, repl, label, flags=re.S):
    global s
    s2, count = re.subn(pattern, repl, s, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 regex match, got {count}')
    s = s2

# ---------------------------------------------------------------------------
# State: the trace of the other godmode proved that Hunger remains real while
# Humanoid.Health becomes NaN after damage. Keep that behavior separate from
# Auto Eat and add a dedicated night camp lock.
# ---------------------------------------------------------------------------
once(
'''    diamondFarm = false,\n    fullbright = true,\n''',
'''    diamondFarm = false,\n    fullbright = true,\n    nanHealthGodmode = true,\n    nightCampLock = false,\n''',
    'state godmode/night fields',
)
once(
'''    foodInterval = 60,\n    lastFoodService = 0,\n''',
'''    foodInterval = 20,\n    foodBatchLimit = 64,\n    lastFoodService = 0,\n''',
    'food batching state',
)

# ---------------------------------------------------------------------------
# NaN health guard. The supplied trace showed Health -> NaN with Hunger still
# decreasing normally. This keeps the stock Hunger value/UI untouched while
# preventing health-based starvation/entity damage from producing a finite
# lethal health value.
# ---------------------------------------------------------------------------
anchor = '''-- Entity-damage protection. Hunger itself is intentionally untouched so the\n-- real Hunger bar can be watched.\nlocal lastSafeCFrame = nil\n\nlocal function protectCharacter(character)\n'''
replacement = '''-- Entity-damage protection. Hunger itself is intentionally untouched so the\n-- real Hunger bar can be watched. The separate trace of the reference godmode\n-- showed its durable state is Humanoid.Health = NaN, not a Hunger spoof.\nlocal lastSafeCFrame = nil\n\nlocal function healthIsNaN(value)\n    return type(value) == "number" and value ~= value\nend\n\nlocal function applyNaNHealthGodmode(humanoid)\n    if not state.active or not state.nanHealthGodmode or not humanoid or not humanoid.Parent then\n        return false\n    end\n    local current = humanoid.Health\n    if not healthIsNaN(current) then\n        pcall(function()\n            humanoid.Health = 0 / 0\n        end)\n    end\n    return healthIsNaN(humanoid.Health)\nend\n\nstate.applyNaNHealthGodmode = applyNaNHealthGodmode\n\nlocal function protectCharacter(character)\n'''
once(anchor, replacement, 'insert NaN health guard')

once(
'''    pcall(function()\n        humanoid.BreakJointsOnDeath = false\n        humanoid.RequiresNeck = false\n        humanoid:SetStateEnabled(Enum.HumanoidStateType.Dead, false)\n    end)\n\n    if not character:FindFirstChild("SB99_GodForceField") then\n''',
'''    pcall(function()\n        humanoid.BreakJointsOnDeath = false\n        humanoid.RequiresNeck = false\n        humanoid:SetStateEnabled(Enum.HumanoidStateType.Dead, false)\n    end)\n    applyNaNHealthGodmode(humanoid)\n\n    if not character:FindFirstChild("SB99_GodForceField") then\n''',
    'arm NaN health on character',
)

regex_once(
    r'''    track\(humanoid\.HealthChanged:Connect\(function\(health\)\n        if not state\.active then\n            return\n        end\n\n        if health < humanoid\.MaxHealth then\n            pcall\(function\(\)\n                humanoid\.Health = humanoid\.MaxHealth\n            end\)\n        end\n    end\)\)''',
'''    track(humanoid.HealthChanged:Connect(function(health)\n        if not state.active then\n            return\n        end\n\n        if state.nanHealthGodmode then\n            if not healthIsNaN(health) then\n                task.defer(applyNaNHealthGodmode, humanoid)\n            end\n        elseif health < humanoid.MaxHealth then\n            pcall(function()\n                humanoid.Health = humanoid.MaxHealth\n            end)\n        end\n    end))''',
    'HealthChanged NaN guard',
)

once(
'''        if humanoid then\n            pcall(function()\n                humanoid.BreakJointsOnDeath = false\n                humanoid:SetStateEnabled(Enum.HumanoidStateType.Dead, false)\n                if humanoid.Health < humanoid.MaxHealth then\n                    humanoid.Health = humanoid.MaxHealth\n                end\n            end)\n        end\n''',
'''        if humanoid then\n            pcall(function()\n                humanoid.BreakJointsOnDeath = false\n                humanoid:SetStateEnabled(Enum.HumanoidStateType.Dead, false)\n                if state.nanHealthGodmode then\n                    applyNaNHealthGodmode(humanoid)\n                elseif humanoid.Health < humanoid.MaxHealth then\n                    humanoid.Health = humanoid.MaxHealth\n                end\n            end)\n        end\n''',
    'anti-void health maintenance',
)

# ---------------------------------------------------------------------------
# Night: stay standing on MainFire and remain anchored there. Stronghold keeps
# priority because its ownership branch runs before the night branch.
# ---------------------------------------------------------------------------
once(
'''    -- Unknown phase is treated as daytime. The game's custom lighting can use\n    -- a nighttime ClockTime while the actual gameplay phase is visibly day.\n    return false\nend\n\n--==============================================================\n-- AUTO FARM MOVEMENT / FOOD SERVICE\n''',
'''    -- Unknown phase is treated as daytime. The game's custom lighting can use\n    -- a nighttime ClockTime while the actual gameplay phase is visibly day.\n    return false\nend\n\nlocal function getNightCampCFrame()\n    local fire = getMainFire()\n    if fire then\n        local center = fire:FindFirstChild("Center", true)\n            or fire:FindFirstChild("InnerTouchZone", true)\n            or getPart(fire)\n        if center and center:IsA("BasePart") then\n            local standY = center.Position.Y + math.max(2.8, center.Size.Y * 0.5 + 2.5)\n            return CFrame.new(center.Position.X, standY, center.Position.Z)\n        end\n    end\n    return CFrame.new(CAMPFIRE_DROP + Vector3.new(0, 3, 0))\nend\n\n--==============================================================\n-- AUTO FARM MOVEMENT / FOOD SERVICE\n''',
    'night camp CFrame',
)

once(
'''            local shouldAnchor = root.Position.Y < -20 and not state.strongholdControl\n            if root.Anchored ~= shouldAnchor then\n''',
'''            local shouldAnchor = (state.nightCampLock == true and not state.strongholdControl)\n                or (root.Position.Y < -20 and not state.strongholdControl)\n            if root.Anchored ~= shouldAnchor then\n''',
    'night anchor in farm lock',
)

once(
'''    state.autoFarm = true\n    state.autoChop = true\n''',
'''    state.autoFarm = true\n    state.nightCampLock = false\n    state.autoChop = true\n''',
    'enable clears night lock',
)

once(
'''    if character then\n        if isNight() then\n            pcall(character.PivotTo, character, CFrame.new(FARM_HOME))\n        elseif root then\n''',
'''    if character then\n        if isNight() then\n            state.nightCampLock = true\n            pcall(character.PivotTo, character, getNightCampCFrame())\n        elseif root then\n''',
    'enable starts on campfire at night',
)

once(
'''    state.autoFarm = false\n    state.focusTree = nil\n''',
'''    state.autoFarm = false\n    state.nightCampLock = false\n    state.focusTree = nil\n''',
    'disable clears night lock',
)

once(
'''    if state.strongholdControl then\n        state.releaseFarmForStronghold()\n    else\n        lockFarmCharacter()\n    end\nend))\n''',
'''    if state.strongholdControl then\n        state.nightCampLock = false\n        state.releaseFarmForStronghold()\n    else\n        lockFarmCharacter()\n    end\nend))\n''',
    'heartbeat releases night lock for stronghold',
)

once(
'''        if state.strongholdControl then\n            state.releaseFarmForStronghold()\n        else\n            local root = character:FindFirstChild("HumanoidRootPart")\n            if isNight() then\n                pcall(character.PivotTo, character, CFrame.new(FARM_HOME))\n            elseif root then\n''',
'''        if state.strongholdControl then\n            state.nightCampLock = false\n            state.releaseFarmForStronghold()\n        else\n            local root = character:FindFirstChild("HumanoidRootPart")\n            if isNight() then\n                state.nightCampLock = true\n                pcall(character.PivotTo, character, getNightCampCFrame())\n            elseif root then\n                state.nightCampLock = false\n''',
    'respawn night camp position',
)

once(
'''            if not state.autoFarm then\n                state.focusTree = nil\n                wasNight = false\n''',
'''            if not state.autoFarm then\n                state.nightCampLock = false\n                state.focusTree = nil\n                wasNight = false\n''',
    'farm loop inactive clears night lock',
)

once(
'''            if state.strongholdControl then\n                state.focusTree = nil\n                state.releaseFarmForStronghold()\n''',
'''            if state.strongholdControl then\n                state.nightCampLock = false\n                state.focusTree = nil\n                state.releaseFarmForStronghold()\n''',
    'farm loop stronghold clears night lock',
)

regex_once(
    r'''            local night = isNight\(\)\n            if night then\n                state\.focusTree = nil\n                if not wasNight then cancelFarmTween\(\) end\n                local character = getCharacter\(\)\n                local root = getRoot\(\)\n                if character and \(not root or \(root\.Position - FARM_HOME\)\.Magnitude > 1\.5\) then\n                    pcall\(character\.PivotTo, character, CFrame\.new\(FARM_HOME\)\)\n                end\n                lockFarmCharacter\(\)\n                wasNight = true\n                if state\.emergencyFoodRun or foodServiceDue\(\) then runFoodService\(\) end\n                task\.wait\(0\.5\)\n                return\n            end\n\n            wasNight = false''',
'''            local night = isNight()\n            if night then\n                state.focusTree = nil\n                state.nightCampLock = true\n                cancelFarmTween()\n                local character = getCharacter()\n                local root = getRoot()\n                local campCF = getNightCampCFrame()\n                if character and (not root or (root.Position - campCF.Position).Magnitude > 1.0) then\n                    pcall(character.PivotTo, character, campCF)\n                end\n                lockFarmCharacter()\n                wasNight = true\n                -- Never launch the gathering service at night because that service\n                -- moves items/camera and used to pull the player away from camp.\n                if (getRealHunger() or state.maxHunger) <= state.eatThreshold then\n                    attemptAutoEat()\n                end\n                task.wait(0.35)\n                return\n            end\n\n            state.nightCampLock = false\n            wasNight = false''',
    'night controller campfire lock',
)

# ---------------------------------------------------------------------------
# Faster food gathering. The place-backed drag API is still used, but this
# path is serialized and intentionally short; resource service is already
# paused while foodServiceRunning is true, so it cannot fight this drag owner.
# ---------------------------------------------------------------------------
food_anchor = '''local function runFoodService()\n'''
fast_food = '''local function fastFoodTransport(item, destination)\n    if not item or not item.Parent then return false end\n    if not isLive(StartDragging) or not isLive(StopDragging) then refreshRemotes() end\n    if not isLive(StartDragging) or not isLive(StopDragging) then return false end\n    if not acquireDragLock(0.45) then return false end\n\n    local ok = pcall(function()\n        if StartDragging:IsA("RemoteEvent") then\n            StartDragging:FireServer(item)\n        else\n            callUtilityRemote(StartDragging, 0.4, item)\n        end\n        task.wait(0.025)\n        if not item.Parent then return end\n        if item:IsA("Model") then\n            item:PivotTo(destination)\n        elseif item:IsA("BasePart") then\n            item.CFrame = destination\n        end\n        task.wait(0.035)\n        if item.Parent then\n            if StopDragging:IsA("RemoteEvent") then\n                StopDragging:FireServer(item)\n            else\n                callUtilityRemote(StopDragging, 0.4, item)\n            end\n        end\n    end)\n    dragBusy = false\n    return ok\nend\n\nlocal function runFoodService()\n'''
once(food_anchor, fast_food, 'insert fast food transport')

regex_once(
    r'''local function runFoodService\(\)\n    if not state\.autoFarm or state\.foodServiceRunning or state\.strongholdControl then\n        return\n    end\n\n    state\.foodServiceRunning = true\n    state\.emergencyFoodRun = false\n    cancelFarmTween\(\)\n\n    local serviceOk = pcall\(function\(\)\n        local character = getCharacter\(\)\n        local servicePosition = isNight\(\) and FARM_HOME or CHILD_CAMP_DROP\n        if character then\n            pcall\(character\.PivotTo, character, CFrame\.new\(servicePosition\)\)\n        end\n        lockFarmCharacter\(\)\n\n        local items = workspace:FindFirstChild\("Items"\)\n        if items then\n            local foods = \{\}\n\n            -- Snapshot before requests can replace/remove raw food\.\n            for _, item in ipairs\(items:GetChildren\(\)\) do\n                if isFoodItem\(item\) then\n                    table\.insert\(foods, item\)\n                end\n            end\n\n            local index = 0\n            for _, item in ipairs\(foods\) do\n                if not state\.autoFarm then\n                    break\n                end\n\n                if item and item\.Parent then\n                    index = index \+ 1\n                    local column = \(index - 1\) % 7\n                    local row = math\.floor\(\(index - 1\) / 7\) % 5\n                    local offset = Vector3\.new\(\n                        \(column - 3\) \* 1\.6,\n                        0,\n                        \(row - 2\) \* 1\.6\n                    \)\n\n                    dragItemTo\(item, CFrame\.new\(FOOD_AREA \+ offset\)\)\n                    task\.wait\(0\.025\)\n\n                    if item\.Parent and isCookable\(item\) then\n                        cookItem\(item\)\n                        task\.wait\(0\.025\)\n                    end\n                end\n            end\n\n            -- Give cooked replacements time to appear\.\n            task\.wait\(3\)\n\n            if \(getRealHunger\(\) or state\.maxHunger\) <= state\.eatThreshold then\n                attemptAutoEat\(\)\n            end\n        end\n    end\)\n\n    state\.lastFoodService = os\.clock\(\)\n    state\.foodServiceRunning = false\n\n    if not serviceOk and state\.autoFarm then\n        state\.emergencyFoodRun = true\n    end\nend''',
'''local function runFoodService()\n    if not state.autoFarm or state.foodServiceRunning or state.strongholdControl then\n        return\n    end\n    if isNight() then\n        if (getRealHunger() or state.maxHunger) <= state.eatThreshold then\n            attemptAutoEat()\n        end\n        state.lastFoodService = os.clock()\n        return\n    end\n\n    state.foodServiceRunning = true\n    state.emergencyFoodRun = false\n\n    local serviceOk = pcall(function()\n        local items = workspace:FindFirstChild("Items")\n        if not items then return end\n\n        local foods = {}\n        for _, item in ipairs(items:GetChildren()) do\n            if isFoodItem(item) then\n                table.insert(foods, item)\n            end\n        end\n        table.sort(foods, function(a, b)\n            local ac = isCooked(a) and 1 or 0\n            local bc = isCooked(b) and 1 or 0\n            if ac ~= bc then return ac > bc end\n            return (tonumber(a:GetAttribute("RestoreHunger")) or 0) > (tonumber(b:GetAttribute("RestoreHunger")) or 0)\n        end)\n\n        local limit = math.min(#foods, tonumber(state.foodBatchLimit) or 64)\n        for index = 1, limit do\n            if not state.autoFarm or state.strongholdControl or isNight() then break end\n            local item = foods[index]\n            if item and item.Parent then\n                local column = (index - 1) % 8\n                local row = math.floor((index - 1) / 8) % 6\n                local offset = Vector3.new((column - 3.5) * 1.25, 0, (row - 2.5) * 1.25)\n                local destination = CFrame.new(FOOD_AREA + offset)\n                if not fastFoodTransport(item, destination) then\n                    dragItemTo(item, destination)\n                end\n                if item.Parent and isCookable(item) then\n                    cookItem(item)\n                end\n                task.wait(0.012)\n            end\n        end\n\n        -- Cooked replacements appear quickly; do not stall patrol for 3 seconds.\n        task.wait(0.65)\n        if (getRealHunger() or state.maxHunger) <= state.eatThreshold then\n            attemptAutoEat()\n        end\n    end)\n\n    state.lastFoodService = os.clock()\n    state.foodServiceRunning = false\n    if not serviceOk and state.autoFarm then\n        state.emergencyFoodRun = true\n    end\nend''',
    'replace food service with rapid batch',
)

# ---------------------------------------------------------------------------
# Camp progression. Remove the fake hardcoded max Bench 8 assumption. Discover
# actual Crafting Bench blueprints / UI tiers at runtime. Known beds keep their
# real progression fallbacks, but runtime CraftingDatabase/UI data wins.
# ---------------------------------------------------------------------------
regex_once(
    r'''-- Camp progression\. Known bed order is preserved, then newer bench tiers\n-- and any additional bed blueprints are discovered from CraftingDatabase\.\nlocal BASE_CAMP_BUILD_QUEUE = \{.*?\nlocal function markCampBuildDone\(itemName\)''',
'''-- Place-backed camp progression. The game exposes blueprint tiers through\n-- CraftingDatabase and the CraftingTable TierN UI. Do not invent Bench 6-8 if\n-- the current place only contains fewer tiers.\nlocal KNOWN_BED_TIERS = {\n    ["Old Bed"] = 2,\n    ["Regular Bed"] = 3,\n    ["Good Bed"] = 4,\n    ["Giant Bed"] = 5,\n}\n\nlocal KNOWN_BED_OFFSETS = {\n    ["Old Bed"] = Vector3.new(-24, 0, 18),\n    ["Regular Bed"] = Vector3.new(-34, 0, 4),\n    ["Good Bed"] = Vector3.new(-27, 0, -18),\n    ["Giant Bed"] = Vector3.new(2, 0, 36),\n}\n\nlocal function blueprintTierFromGroup(groupKey, blueprint)\n    for _, field in ipairs({ "Tier", "RequiredTier", "CraftingTier", "BenchLevel", "RequiredBenchLevel" }) do\n        local value = type(blueprint) == "table" and tonumber(blueprint[field]) or nil\n        if value then return math.max(1, math.floor(value)) end\n    end\n    local text = tostring(groupKey or "")\n    return tonumber(string.match(text, "[Tt]ier%s*(%d+)"))\n        or tonumber(string.match(text, "(%d+)"))\nend\n\nlocal function discoverCampBuildQueue()\n    local maxBench = 1\n    local beds = {}\n    local seenBeds = {}\n    local database = getCraftingDatabase()\n    local blueprints = database and database.PossibleBlueprints\n\n    if type(blueprints) == "table" then\n        for groupKey, group in pairs(blueprints) do\n            if type(group) == "table" then\n                for _, blueprint in pairs(group) do\n                    if type(blueprint) == "table" and type(blueprint.Name) == "string" then\n                        local name = blueprint.Name\n                        local bench = tonumber(string.match(name, "^Crafting Bench (%d+)$"))\n                        local tier = blueprintTierFromGroup(groupKey, blueprint)\n                        if bench then\n                            maxBench = math.max(maxBench, bench)\n                        elseif string.find(string.lower(name), "bed", 1, true) then\n                            local required = tier or KNOWN_BED_TIERS[name] or 1\n                            if not seenBeds[name] then\n                                seenBeds[name] = true\n                                table.insert(beds, { name = name, tier = required })\n                            end\n                        end\n                    end\n                end\n            end\n        end\n    end\n\n    local interface = playerGui:FindFirstChild("Interface")\n    local crafting = interface and interface:FindFirstChild("CraftingTable")\n    local scrolling = crafting and crafting:FindFirstChild("ScrollingFrame")\n    if scrolling then\n        for _, tierFrame in ipairs(scrolling:GetChildren()) do\n            local tier = tonumber(string.match(tierFrame.Name, "^Tier(%d+)$"))\n            if tier then\n                maxBench = math.max(maxBench, tier)\n                for _, entry in ipairs(tierFrame:GetChildren()) do\n                    if string.find(string.lower(entry.Name), "bed", 1, true) and not seenBeds[entry.Name] then\n                        seenBeds[entry.Name] = true\n                        table.insert(beds, { name = entry.Name, tier = tier })\n                    end\n                end\n            end\n        end\n    end\n\n    -- Current place has a finite progression. If replication has not exposed\n    -- the database/UI yet, fall back only to the known five-tier bed tree.\n    if maxBench <= 1 then maxBench = 5 end\n    for name, tier in pairs(KNOWN_BED_TIERS) do\n        if not seenBeds[name] then\n            seenBeds[name] = true\n            table.insert(beds, { name = name, tier = tier })\n        end\n    end\n\n    table.sort(beds, function(a, b)\n        if a.tier ~= b.tier then return a.tier < b.tier end\n        local aw, as = getCraftCost(a.name)\n        local bw, bs = getCraftCost(b.name)\n        local ac = (aw or 0) + (as or 0)\n        local bc = (bw or 0) + (bs or 0)\n        if ac ~= bc then return ac < bc end\n        return a.name < b.name\n    end)\n\n    local queue = {}\n    local bedIndex = 0\n    for tier = 2, maxBench do\n        local benchName = "Crafting Bench " .. tostring(tier)\n        local wood, scrap = getCraftCost(benchName)\n        if wood ~= nil and scrap ~= nil then\n            table.insert(queue, { kind = "bench", name = benchName, benchLevel = tier })\n        end\n        for _, bed in ipairs(beds) do\n            if bed.tier == tier then\n                bedIndex += 1\n                local offset = KNOWN_BED_OFFSETS[bed.name]\n                if not offset then\n                    local angle = ((bedIndex - 1) / math.max(1, #beds)) * math.pi * 2\n                    offset = Vector3.new(math.cos(angle) * 42, 0, math.sin(angle) * 42)\n                end\n                table.insert(queue, { kind = "bed", name = bed.name, tier = tier, offset = offset })\n            end\n        end\n    end\n    return queue, maxBench\nend\n\nlocal function markCampBuildDone(itemName)''',
    'replace camp progression discovery',
)

# Placement: multiple verified positions, equip crafted structure first, and do
# not teleport the player away from normal Auto Farm just to place a bed.
regex_once(
    r'''local function placeCampStructure\(item, offset\)\n.*?\nend\n\n-- Place-backed camp progression''',
'''local function placeCampStructure(item, offset)\n    if not item or not item.Parent then return false end\n    if not isLive(RequestPlaceStructure) then refreshRemotes() end\n    if not isLive(RequestPlaceStructure) then return false end\n\n    equipOwnedItem(item)\n    local base = offset or Vector3.new(35, 0, 0)\n    local attempts = {\n        base,\n        base + Vector3.new(5, 0, 0),\n        base + Vector3.new(-5, 0, 0),\n        base + Vector3.new(0, 0, 5),\n        base + Vector3.new(0, 0, -5),\n        Vector3.new(-base.Z, 0, base.X),\n        Vector3.new(base.Z, 0, -base.X),\n    }\n\n    for _, tryOffset in ipairs(attempts) do\n        if not item.Parent then return true end\n        local placePos, center = getGroundPositionAroundCamp(tryOffset)\n        placePos += Vector3.new(0, 0.15, 0)\n        local placeCF = CFrame.lookAt(placePos, Vector3.new(center.X, placePos.Y, center.Z))\n        local placement = { Valid = true, CFrame = placeCF, Position = placePos }\n        local ok, response = callUtilityRemote(RequestPlaceStructure, 1.5, item, placement, placeCF)\n        local accepted = ok and response ~= false\n            and not (type(response) == "table" and response.Success == false)\n        if accepted then\n            local deadline = os.clock() + 1.25\n            repeat\n                if not item.Parent or worldHasCampStructure(item.Name) then return true end\n                task.wait(0.08)\n            until os.clock() >= deadline\n        end\n        task.wait(0.08)\n    end\n    return worldHasCampStructure(item.Name)\nend\n\n-- Place-backed camp progression''',
    'robust bed placement',
)

# Replace the service: upgrade all actually-present bench tiers, verify accepted
# craft responses, and never let one failed bed placement permanently block the
# rest of the progression. It retries unfinished beds on following passes.
regex_once(
    r'''local function runCampBuildService\(\)\n.*?\nend\n\nlocal function plantAvailableSaplings\(\)''',
'''local function campCraftAccepted(response)\n    if response == false then return false end\n    if type(response) == "table" and response.Success == false then return false end\n    return true\nend\n\nlocal function craftCampBlueprint(name)\n    if not isLive(CraftItem) then refreshRemotes() end\n    if not isLive(CraftItem) then return false end\n    for _ = 1, 2 do\n        local ok, response = callUtilityRemote(CraftItem, 1.75, name)\n        if ok and campCraftAccepted(response) then return true end\n        task.wait(0.12)\n    end\n    return false\nend\n\nlocal function runCampBuildService()\n    if not state.active\n        or not state.autoFarm\n        or not state.smartResources\n        or state.campBuildRunning\n        or state.childRescueRunning\n        or state.foodServiceRunning\n        or state.resourceServiceRunning\n        or not state.autoCampBuild\n        or state.strongholdControl\n        or isNight() then\n        return\n    end\n\n    local fireLevel = getCampfireLevel()\n    if fireLevel == nil or fireLevel < state.campfireTargetLevel then return end\n    local now = os.clock()\n    if now - state.lastCampBuild < state.campBuildInterval then return end\n    state.lastCampBuild = now\n    state.campBuildRunning = true\n\n    local serviceOk = pcall(function()\n        local campground = getCampground()\n        if not campground then return end\n        local queue, maxBench = discoverCampBuildQueue()\n        currentCraftingBenchLevel()\n        local completed = 0\n\n        for _, spec in ipairs(queue) do\n            if not state.active or not state.autoFarm or state.strongholdControl or isNight() then break end\n            if campBuildIsDone(spec) then continue end\n\n            local woodCost, scrapCost = getCraftCost(spec.name)\n            if woodCost == nil or scrapCost == nil then\n                -- A UI-only entry that is not a craftable blueprint must not\n                -- block later real tiers/beds.\n                continue\n            end\n            local totalWood = tonumber(campground:GetAttribute("TotalWood")) or 0\n            local totalScrap = tonumber(campground:GetAttribute("TotalScrap")) or 0\n            if totalWood < woodCost or totalScrap < scrapCost then\n                -- Keep scanning: a later zero-cost/owned structure may still be placeable.\n                continue\n            end\n\n            if spec.kind == "bench" then\n                if craftCampBlueprint(spec.name) then\n                    state.campBenchLevel = math.max(tonumber(state.campBenchLevel) or 1, spec.benchLevel or 1)\n                    markCampBuildDone(spec.name)\n                    completed += 1\n                    task.wait(0.28)\n                end\n            else\n                local item = findOwnedNamedItem(spec.name)\n                if not item and craftCampBlueprint(spec.name) then\n                    local deadline = os.clock() + 2.25\n                    repeat\n                        task.wait(0.06)\n                        item = findOwnedNamedItem(spec.name)\n                    until item or not state.autoFarm or state.strongholdControl or os.clock() >= deadline\n                end\n\n                if item and item.Parent and placeCampStructure(item, spec.offset) then\n                    markCampBuildDone(spec.name)\n                    completed += 1\n                    task.wait(0.12)\n                end\n            end\n\n            if completed >= math.max(8, maxBench + 2) then break end\n        end\n    end)\n\n    state.campBuildRunning = false\n    if not serviceOk then state.lastCampBuild = 0 end\nend\n\nlocal function plantAvailableSaplings()''',
    'replace camp build service',
)

# ---------------------------------------------------------------------------
# UI: persistent Stronghold countdown and NaN godmode toggle.
# ---------------------------------------------------------------------------
once(
'''makeToggle(farmSection, "Fullbright + No Fog", function() return state.fullbright end, function(v)\n    state.fullbright = v\n    if v then\n        state.applyFullbright()\n    else\n        state.restoreFullbright()\n    end\nend, false)\n''',
'''makeToggle(farmSection, "Fullbright + No Fog", function() return state.fullbright end, function(v)\n    state.fullbright = v\n    if v then\n        state.applyFullbright()\n    else\n        state.restoreFullbright()\n    end\nend, false)\nmakeToggle(farmSection, "NaN Health Godmode", function() return state.nanHealthGodmode end, function(v)\n    state.nanHealthGodmode = v\n    local humanoid = getHumanoid()\n    if humanoid then\n        if v then\n            applyNaNHealthGodmode(humanoid)\n        elseif healthIsNaN(humanoid.Health) then\n            pcall(function() humanoid.Health = humanoid.MaxHealth end)\n        end\n    end\nend, false)\n''',
    'godmode UI toggle',
)

stronghold_toggle = '''makeToggle(strongholdSection, "Diamond Farm", function() return state.diamondFarm end, function(v)\n    state.diamondFarm = v\n    state.strongholdControl = false\n    state.strongholdRunning = false\n    state.strongholdBaseline = nil\n    state.strongholdAttemptActive = false\n    state.strongholdRetryAt = 0\n    state.strongholdCycleComplete = false\n    state.strongholdStatus = v and "Waiting" or "Off"\nend, true)\n'''
stronghold_plus = stronghold_toggle + '''\nlocal strongholdCounter = Instance.new("TextLabel")\nstrongholdCounter.Size = UDim2.new(1, 0, 0, 34)\nstrongholdCounter.BackgroundColor3 = Color3.fromRGB(31, 31, 38)\nstrongholdCounter.BorderSizePixel = 0\nstrongholdCounter.TextColor3 = Color3.fromRGB(235, 235, 242)\nstrongholdCounter.Font = Enum.Font.GothamBold\nstrongholdCounter.TextSize = 10\nstrongholdCounter.TextXAlignment = Enum.TextXAlignment.Left\nstrongholdCounter.LayoutOrder = #strongholdSection:GetChildren() + 1\nstrongholdCounter.Parent = strongholdSection\nrounded(strongholdCounter, 7)\ntable.insert(refreshers, function()\n    strongholdCounter.Text = "   Countdown: " .. tostring(state.strongholdCountdown or "--")\n        .. "   |   " .. tostring(state.strongholdStatus or "Waiting")\nend)\n'''
once(stronghold_toggle, stronghold_plus, 'Stronghold countdown UI')

once(
'''            "Fire %s/6 | Axe %s | Trees %d | Hit T%d/E%d\\nSmart %s | Light %s | Diamonds %s",\n''',
'''            "Fire %s/6 | Axe %s | Trees %d | Hit T%d/E%d\\nSmart %s | SH %s | Diamonds %s",\n''',
    'status format countdown label',
)
once(
'''            state.smartResources and "ON" or "OFF",\n            state.fullbright and "ON" or "OFF",\n            diamonds and tostring(diamonds) or "--"\n''',
'''            state.smartResources and "ON" or "OFF",\n            tostring(state.strongholdCountdown or "--"),\n            diamonds and tostring(diamonds) or "--"\n''',
    'status countdown value',
)

# Final static assertions encoded into the patched helper comments/structure.
required = [
    'nanHealthGodmode = true',
    'getNightCampCFrame',
    'state.nightCampLock = true',
    'fastFoodTransport',
    'discoverCampBuildQueue',
    'campCraftAccepted',
    'Countdown: ',
    'NaN Health Godmode',
    'RequestPlaceStructure',
    'InteractionHandler',
    'RequestScrapItem',
]
for token in required:
    if token not in s:
        raise SystemExit(f'missing patched token: {token}')

TARGET.write_text(s, encoding='utf-8')
print('patched bytes', len(s.encode('utf-8')))
