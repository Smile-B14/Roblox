from pathlib import Path
import re

path = Path("99 Nights Helper Godmode")
text = path.read_text()


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, got {count}")
    text = text.replace(old, new, 1)


def regex_once(pattern: str, new: str, label: str) -> None:
    global text
    updated, count = re.subn(pattern, new, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{label}: expected one regex match, got {count}")
    text = updated


replace_once(
    "    nightCampLock = false,\n",
    "    nightCampLock = false,\n"
    "    nightClockSeenDay = false,\n"
    "    nightClockFallback = false,\n"
    "    nightClockCandidateSince = nil,\n",
    "night state",
)

new_night = '''state.normalizeNightValue = function(value, invert)
    local result = nil
    if type(value) == "boolean" then
        result = value
    elseif type(value) == "number" and (value == 0 or value == 1) then
        result = value == 1
    elseif type(value) == "string" then
        local lowered = string.lower(value)
        if lowered == "true" or lowered == "1" or lowered == "night" or lowered == "nighttime" then
            result = true
        elseif lowered == "false" or lowered == "0" or lowered == "day" or lowered == "daytime" then
            result = false
        end
    end
    if result ~= nil and invert then
        result = not result
    end
    return result
end

local function isNight()
    local sources = {}
    local map = workspace:FindFirstChild("Map")
    local campground = map and map:FindFirstChild("Campground")
    table.insert(sources, workspace)
    if map then table.insert(sources, map) end
    if campground then table.insert(sources, campground) end
    table.insert(sources, Lighting)

    local boolSignals = {
        { "IsNight", false }, { "Night", false }, { "Nighttime", false },
        { "IsNightTime", false }, { "NightActive", false }, { "NightStarted", false },
        { "IsDay", true }, { "Daytime", true }, { "IsDayTime", true }, { "DayActive", true },
    }
    for _, object in ipairs(sources) do
        for _, signal in ipairs(boolSignals) do
            local name, invert = signal[1], signal[2]
            local ok, value = pcall(object.GetAttribute, object, name)
            local result = ok and state.normalizeNightValue(value, invert) or nil
            if result ~= nil then
                if result == false then
                    state.nightClockSeenDay = true
                    state.nightClockFallback = false
                    state.nightClockCandidateSince = nil
                end
                return result
            end

            local child = object:FindFirstChild(name)
            if child and (child:IsA("BoolValue") or child:IsA("IntValue")
                or child:IsA("NumberValue") or child:IsA("StringValue")) then
                local valueOk, childValue = pcall(function() return child.Value end)
                result = valueOk and state.normalizeNightValue(childValue, invert) or nil
                if result ~= nil then
                    if result == false then
                        state.nightClockSeenDay = true
                        state.nightClockFallback = false
                        state.nightClockCandidateSince = nil
                    end
                    return result
                end
            end
        end
    end

    local phaseNames = {
        "Phase", "CurrentPhase", "GamePhase", "Cycle", "CycleState", "TimeOfDay",
        "TimeState", "DayNightState", "DayNightCycle", "WorldPhase",
    }
    for _, object in ipairs(sources) do
        for _, name in ipairs(phaseNames) do
            local ok, value = pcall(object.GetAttribute, object, name)
            if ok and type(value) == "string" then
                local phase = string.lower(value)
                if string.find(phase, "night", 1, true) then return true end
                if string.find(phase, "day", 1, true)
                    or string.find(phase, "dawn", 1, true)
                    or string.find(phase, "morning", 1, true) then
                    state.nightClockSeenDay = true
                    state.nightClockFallback = false
                    state.nightClockCandidateSince = nil
                    return false
                end
            end

            local child = object:FindFirstChild(name)
            if child and child:IsA("StringValue") then
                local phase = string.lower(child.Value)
                if string.find(phase, "night", 1, true) then return true end
                if string.find(phase, "day", 1, true)
                    or string.find(phase, "dawn", 1, true)
                    or string.find(phase, "morning", 1, true) then
                    state.nightClockSeenDay = true
                    state.nightClockFallback = false
                    state.nightClockCandidateSince = nil
                    return false
                end
            end
        end
    end

    -- Use ClockTime only after this execution has observed a real daytime clock
    -- window. This keeps the old false-night Day 1 startup case from returning.
    local clock = tonumber(Lighting.ClockTime)
    if clock ~= nil then
        local dayClock = clock >= 6.25 and clock < 17.75
        local nightClock = clock >= 18.25 or clock < 5.75
        local now = os.clock()
        if dayClock then
            state.nightClockSeenDay = true
            state.nightClockFallback = false
            state.nightClockCandidateSince = nil
        elseif nightClock and state.nightClockSeenDay then
            if state.nightClockCandidateSince == nil then
                state.nightClockCandidateSince = now
            elseif now - state.nightClockCandidateSince >= 0.65 then
                state.nightClockFallback = true
            end
        else
            state.nightClockCandidateSince = nil
        end
    end
    return state.nightClockFallback == true
end

'''
regex_once(
    r'local function isNight\(\)\n.*?\nend\n\n(?=state\.getNightCampCFrame = function\(\))',
    new_night,
    "night detector",
)

regex_once(
    r'state\.getNightCampCFrame = function\(\)\n.*?\nend\n\n(?=--=+\n-- AUTO FARM MOVEMENT / FOOD SERVICE)',
    '''state.getNightCampCFrame = function()
    local fire = getMainFire()
    if fire then
        local center = fire:FindFirstChild("Center", true)
            or fire:FindFirstChild("InnerTouchZone", true)
            or getPart(fire)
        if center and center:IsA("BasePart") then
            return center.CFrame * CFrame.new(0, -40, 0)
        end
    end
    return CFrame.new(FARM_HOME)
end

''',
    "night shelter",
)

replace_once(
    '    ["washing machine"] = true,\n    ["cultist experiment"] = true,\n',
    '    ["washing machine"] = true,\n    ["cultist gem"] = true,\n    ["cultist experiment"] = true,\n',
    "cultist gem name",
)
replace_once(
    '''    local name = lowerName(item)
    for _, pattern in ipairs(PROTECTED_RESOURCE_PATTERNS) do
''',
    '''    local name = lowerName(item)
    if string.find(name, "cultist", 1, true) and string.find(name, "gem", 1, true) then
        return false
    end
    for _, pattern in ipairs(PROTECTED_RESOURCE_PATTERNS) do
''',
    "cultist gem protection exception",
)

replace_once(
    '        local item = container and container:FindFirstChild(itemName)\n',
    '        local item = container and container:FindFirstChild(itemName, true)\n',
    "recursive owned lookup",
)

regex_once(
    r'local function getGroundPositionAroundCamp\(offset\)\n.*?\nend\n\n(?=local function placeCampStructure)',
    '''local function getGroundPositionAroundCamp(offset)
    local firePart = getPart(getMainFire())
    local center = firePart and firePart.Position or Vector3.new(0, 10, 0)
    local x = center.X + offset.X
    local z = center.Z + offset.Z
    local map = workspace:FindFirstChild("Map")
    local ground = map and map:FindFirstChild("Ground")
    local grass = ground and ground:FindFirstChild("Grass", true)

    -- Current live placement scripts use the Grass Y directly. This also avoids
    -- raycasts landing on an existing bed, bench or campfire part.
    if grass and grass:IsA("BasePart") then
        return Vector3.new(x, grass.Position.Y, z), center
    end

    local params = RaycastParams.new()
    params.FilterType = Enum.RaycastFilterType.Exclude
    local character = getCharacter()
    params.FilterDescendantsInstances = character and { character } or {}
    local hit = workspace:Raycast(
        Vector3.new(x, center.Y + 120, z),
        Vector3.new(0, -300, 0),
        params
    )
    return Vector3.new(x, hit and hit.Position.Y or center.Y, z), center
end

''',
    "placement ground",
)

regex_once(
    r'local function placeCampStructure\(item, offset\)\n.*?\nend\n\n(?=-- Place-backed camp progression\.)',
    '''local function placeCampStructure(item, offset)
    if not item or not item.Parent then return false end
    if not isLive(RequestPlaceStructure) then refreshRemotes() end
    if not isLive(RequestPlaceStructure) then return false end

    -- RequestPlaceStructure accepts the crafted Inventory instance directly.
    -- Equipping it first can move/reparent the instance during validation.
    local base = offset or Vector3.new(35, 0, 0)
    local attempts = {
        base,
        base + Vector3.new(6, 0, 0),
        base + Vector3.new(-6, 0, 0),
        base + Vector3.new(0, 0, 6),
        base + Vector3.new(0, 0, -6),
        Vector3.new(-base.Z, 0, base.X),
        Vector3.new(base.Z, 0, -base.X),
    }

    for _, tryOffset in ipairs(attempts) do
        if not item.Parent then return true end
        local placePos = getGroundPositionAroundCamp(tryOffset)
        local placeCF = CFrame.new(placePos)
        local placement = { Valid = true, CFrame = placeCF, Position = placePos }
        local ok, response = callUtilityRemote(RequestPlaceStructure, 1.75, item, placement, placeCF)
        local accepted = ok and response ~= false
            and not (type(response) == "table" and response.Success == false)
        if accepted then
            local deadline = os.clock() + 1.6
            repeat
                if not item.Parent or worldHasCampStructure(item.Name) then return true end
                task.wait(0.08)
            until os.clock() >= deadline
        end
        task.wait(0.10)
    end
    return worldHasCampStructure(item.Name)
end

''',
    "structure placement",
)

regex_once(
    r'state\.KNOWN_BED_TIERS = \{\n.*?\n\}',
    '''state.KNOWN_BED_TIERS = {
    ["Old Bed"] = 1,
    ["Regular Bed"] = 2,
    ["Good Bed"] = 3,
    ["Giant Bed"] = 4,
}''',
    "bed tiers",
)
replace_once(
    '                        local required = tier or state.KNOWN_BED_TIERS[name] or 1\n',
    '                        local required = state.KNOWN_BED_TIERS[name] or tier or 1\n',
    "bed tier precedence",
)
replace_once(
    '    for tier = 2, maxBench do\n',
    '    for tier = 1, maxBench do\n',
    "tier one queue",
)

old_gate = '''            local woodCost, scrapCost = getCraftCost(spec.name)
            if woodCost == nil or scrapCost == nil then
                -- A UI-only entry that is not a craftable blueprint must not
                -- block later real tiers/beds.
                continue
            end
            local totalWood = tonumber(campground:GetAttribute("TotalWood")) or 0
            local totalScrap = tonumber(campground:GetAttribute("TotalScrap")) or 0
            if totalWood < woodCost or totalScrap < scrapCost then
                -- Keep scanning: a later zero-cost/owned structure may still be placeable.
                continue
            end

            if spec.kind == "bench" then
'''
new_gate = '''            -- A crafted bed must remain placeable even after its purchase already
            -- consumed the required wood/scrap. Do not gate an owned bed on buying it again.
            local ownedItem = spec.kind == "bed" and findOwnedNamedItem(spec.name) or nil
            local woodCost, scrapCost = getCraftCost(spec.name)
            if not ownedItem and (woodCost == nil or scrapCost == nil) then
                continue
            end
            if not ownedItem then
                local totalWood = tonumber(campground:GetAttribute("TotalWood")) or 0
                local totalScrap = tonumber(campground:GetAttribute("TotalScrap")) or 0
                if totalWood < woodCost or totalScrap < scrapCost then
                    continue
                end
            end

            if spec.kind == "bench" then
'''
replace_once(old_gate, new_gate, "owned bed resource gate")
replace_once(
    '''            else
                local item = findOwnedNamedItem(spec.name)
                if not item and state.craftCampBlueprint(spec.name) then
''',
    '''            else
                local item = ownedItem
                if not item and state.craftCampBlueprint(spec.name) then
''',
    "reuse owned bed",
)

replace_once(
    '''    if state.strongholdControl then
        state.nightCampLock = false
        state.releaseFarmForStronghold()
    else
        lockFarmCharacter()
    end
end))
''',
    '''    if state.strongholdControl then
        state.nightCampLock = false
        state.releaseFarmForStronghold()
    else
        if state.nightCampLock then
            local character = getCharacter()
            local root = getRoot()
            local hideCF = state.getNightCampCFrame()
            if character and root and (root.Position - hideCF.Position).Magnitude > 0.75 then
                cancelFarmTween()
                pcall(character.PivotTo, character, hideCF)
            end
        end
        lockFarmCharacter()
    end
end))
''',
    "night heartbeat pin",
)

for marker in (
    '["Old Bed"] = 1',
    'for tier = 1, maxBench do',
    'local ownedItem = spec.kind == "bed" and findOwnedNamedItem(spec.name) or nil',
    'local item = ownedItem',
    'local placeCF = CFrame.new(placePos)',
    '["cultist gem"] = true',
    'return center.CFrame * CFrame.new(0, -40, 0)',
    'state.nightClockFallback == true',
    'pcall(character.PivotTo, character, hideCF)',
):
    if marker not in text:
        raise SystemExit(f"missing marker: {marker}")

path.write_text(text)
