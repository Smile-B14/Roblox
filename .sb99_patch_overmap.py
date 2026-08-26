from pathlib import Path
import re

path = Path('99 Nights Helper Godmode')
s = path.read_text(encoding='utf-8')


def rep(old, new, label):
    global s
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected 1 match, got {count}')
    s = s.replace(old, new, 1)


rep(
    'local Lighting = game:GetService("Lighting")',
    '''local Lighting = game:GetService("Lighting")
local GuiService = game:GetService("GuiService")

-- Hide Roblox's built-in streaming "Gameplay Paused" notification. Streaming
-- itself still happens, so child rescue waits after long-distance teleports.
pcall(function()
    GuiService:SetGameplayPausedNotificationEnabled(false)
end)''',
    'gameplay paused UI'
)

rep(
    'local RequestBagDropItem = nil',
    '''local RequestBagDropItem = nil
local RequestPlantItem = nil
local CraftItem = nil
local RequestPlaceStructure = nil''',
    'new remote declarations'
)

rep(
    '    RequestBagDropItem = findReplicated("RequestBagDropItem")',
    '''    RequestBagDropItem = findReplicated("RequestBagDropItem")
    RequestPlantItem = findReplicated("RequestPlantItem")
    CraftItem = findReplicated("CraftItem")
    RequestPlaceStructure = findReplicated("RequestPlaceStructure")''',
    'new remote resolution'
)

rep(
    '''local FARM_HOME = Vector3.new(0, -50, 0)
local RETURN_POSITION = Vector3.new(0, 50, 0)
local CAMPFIRE_DROP = Vector3.new(0, 13, 0)
local FOOD_AREA = CAMPFIRE_DROP
local SCRAP_DROP = Vector3.new(20, 13, -5)''',
    '''local FARM_HOME = Vector3.new(0, -50, 0)
local FARM_PATROL_Y = 60
local FARM_PLATFORM_Y = -54
local RETURN_POSITION = Vector3.new(0, 50, 0)
local CAMPFIRE_DROP = Vector3.new(0, 13, 0)
local CHILD_CAMP_DROP = Vector3.new(0, 15, 0)
local FOOD_AREA = CAMPFIRE_DROP
local SCRAP_DROP = Vector3.new(20, 13, -5)''',
    'farm positions'
)

rep(
    '''    patrolRadius = 700,
    patrolSpeed = 60,
    patrolIndex = 1,

    campfireTargetLevel = 6,''',
    '''    patrolRadius = 700,
    patrolSpeed = 60,
    strongAxePatrolSpeed = 80,
    patrolIndex = 1,

    saplingInterval = 10,
    lastSaplingPlant = 0,
    saplingRotation = 0,
    saplingServiceRunning = false,
    campBuildInterval = 2,
    lastCampBuild = 0,
    campBuildRunning = false,
    campBuildDone = type(G.SB99_CAMP_BUILD_DONE) == "table" and G.SB99_CAMP_BUILD_DONE or {},

    campfireTargetLevel = 6,''',
    'automation state'
)

rep(
    'G.SB99_STATE = state',
    '''G.SB99_STATE = state
G.SB99_CAMP_BUILD_DONE = state.campBuildDone''',
    'persist camp build state'
)

rep(
    '''    previousState.childRescueRunning = false
    previousState.childRescuePending = false''',
    '''    previousState.childRescueRunning = false
    previousState.childRescuePending = false
    previousState.saplingServiceRunning = false
    previousState.campBuildRunning = false''',
    'previous-run cleanup'
)

rep(
    '    platform.CFrame = CFrame.new(0, -53, 0)',
    '    platform.CFrame = CFrame.new(0, FARM_PLATFORM_Y, 0)',
    'lower platform'
)

rep(
    '''            math.cos(angle) * radius,
            -50,
            math.sin(angle) * radius''',
    '''            math.cos(angle) * radius,
            FARM_PATROL_Y,
            math.sin(angle) * radius''',
    'above-map patrol'
)

rep('            task.wait(0.18)', '            task.wait(2)', 'missing child streaming wait')

rep(
    '''        focusCameraAt(part.Position)
    end

    equipOwnedItem(sack)''',
    '''        focusCameraAt(part.Position)
        -- Long-distance teleports can stream the child region in after the
        -- character arrives. Give it two full seconds before interaction.
        task.wait(2)
    end

    equipOwnedItem(sack)''',
    'child load wait'
)

rep(
    '''            if storeChildInSack(sack, child) then
                stored = stored + 1
            end
            task.wait(0.08)''',
    '''            if storeChildInSack(sack, child) then
                stored = stored + 1
            end
            -- Let the sack replicate before teleporting to the next child.
            task.wait(1)''',
    'between-child wait'
)

rep(
    '        pcall(character.PivotTo, character, CFrame.new(CAMPFIRE_DROP + Vector3.new(0, 3, 4)))',
    '        pcall(character.PivotTo, character, CFrame.new(CHILD_CAMP_DROP))',
    'child camp teleport'
)
rep('    focusCameraAt(CAMPFIRE_DROP)', '    focusCameraAt(CHILD_CAMP_DROP)', 'child camp camera')

rep(
    '    local duration = math.max(0.15, distance / state.patrolSpeed)',
    '''    local patrolSpeed = state.patrolSpeed
    local ownedAxe = select(1, findBestOwned(axeScore))
    if ownedAxe then
        local rank = AXE_FALLBACK[ownedAxe.Name] or 0
        if rank >= (AXE_FALLBACK["Strong Axe"] or 30) then
            patrolSpeed = state.strongAxePatrolSpeed
        end
    end
    local duration = math.max(0.15, distance / patrolSpeed)''',
    'strong axe patrol speed'
)

insert_marker = 'local patrolPoints = {}'
if s.count(insert_marker) != 1:
    raise RuntimeError(f'patrol insertion point: expected 1, got {s.count(insert_marker)}')

automation = r'''--==============================================================
-- CAMP BUILDING / SAPLING ORBIT
--==============================================================

local function getCampground()
    local map = workspace:FindFirstChild("Map")
    return map and map:FindFirstChild("Campground")
end

local craftingDatabase = nil
local function getCraftingDatabase()
    if type(craftingDatabase) == "table" then
        return craftingDatabase
    end

    local databases = ReplicatedStorage:FindFirstChild("Databases")
    local module = databases and databases:FindFirstChild("CraftingDatabase")
    if module and module:IsA("ModuleScript") then
        local ok, result = pcall(require, module)
        if ok and type(result) == "table" then
            craftingDatabase = result
        end
    end
    return craftingDatabase
end

local function getCraftCost(itemName)
    local database = getCraftingDatabase()
    local blueprints = database and database.PossibleBlueprints
    if type(blueprints) ~= "table" then
        return nil, nil
    end

    for _, group in pairs(blueprints) do
        if type(group) == "table" then
            for _, blueprint in pairs(group) do
                if type(blueprint) == "table" and blueprint.Name == itemName then
                    return tonumber(blueprint.WoodPrice) or 0,
                        tonumber(blueprint.ScrapPrice) or 0
                end
            end
        end
    end
    return nil, nil
end

local function findOwnedNamedItem(itemName)
    for _, container in ipairs(ownedContainers()) do
        local item = container and container:FindFirstChild(itemName)
        if item then
            return item
        end
    end
    return nil
end

local function worldHasCampStructure(itemName)
    local structures = workspace:FindFirstChild("Structures")
    if structures and structures:FindFirstChild(itemName, true) then
        return true
    end
    local campground = getCampground()
    return campground ~= nil and campground:FindFirstChild(itemName, true) ~= nil
end

local function currentCraftingBenchLevel()
    local best = 1
    local function scan(root)
        if not root then return end
        for _, object in ipairs(root:GetDescendants()) do
            local level = tonumber(string.match(object.Name, "^Crafting Bench (%d+)$"))
            if level then
                best = math.max(best, level)
            end
        end
    end
    scan(getCampground())
    scan(workspace:FindFirstChild("Structures"))
    return best
end

local function getGroundPositionAroundCamp(offset)
    local firePart = getPart(getMainFire())
    local center = firePart and firePart.Position or Vector3.new(0, 10, 0)
    local x = center.X + offset.X
    local z = center.Z + offset.Z
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

local function placeCampStructure(item, offset)
    if not item or not item.Parent then return false end
    if not isLive(RequestPlaceStructure) then refreshRemotes() end
    if not isLive(RequestPlaceStructure) then return false end

    local placePos, center = getGroundPositionAroundCamp(offset)
    local placeCF = CFrame.lookAt(
        placePos,
        Vector3.new(center.X, placePos.Y, center.Z)
    )
    local placement = {
        Valid = true,
        CFrame = placeCF,
        Position = placePos,
    }
    local ok, response = callUtilityRemote(
        RequestPlaceStructure,
        2,
        item,
        placement,
        placeCF
    )
    return ok and response ~= false
end

-- Confirmed game progression. Keep this exact order because later blueprints
-- depend on the earlier crafting-bench upgrades.
local CAMP_BUILD_QUEUE = {
    { name = "Crafting Bench 2", benchLevel = 2, offset = Vector3.new(22, 0, 14) },
    { name = "Old Bed", offset = Vector3.new(-22, 0, 15) },
    { name = "Regular Bed", offset = Vector3.new(-30, 0, 0) },
    { name = "Crafting Bench 3", benchLevel = 3, offset = Vector3.new(24, 0, 0) },
    { name = "Good Bed", offset = Vector3.new(-22, 0, -15) },
    { name = "Crafting Bench 4", benchLevel = 4, offset = Vector3.new(22, 0, -16) },
    { name = "Giant Bed", offset = Vector3.new(0, 0, 32) },
}

local function markCampBuildDone(itemName)
    state.campBuildDone[itemName] = true
    G.SB99_CAMP_BUILD_DONE = state.campBuildDone
end

local function campBuildIsDone(spec)
    if state.campBuildDone[spec.name] then return true end
    if spec.benchLevel and currentCraftingBenchLevel() >= spec.benchLevel then
        markCampBuildDone(spec.name)
        return true
    end
    if worldHasCampStructure(spec.name) then
        markCampBuildDone(spec.name)
        return true
    end
    return false
end

local function runCampBuildService()
    if not state.active
        or not state.autoFarm
        or not state.smartResources
        or state.campBuildRunning
        or state.childRescueRunning
        or state.foodServiceRunning
        or state.resourceServiceRunning
        or isNight() then
        return
    end

    local level = getCampfireLevel()
    if level == nil or level < state.campfireTargetLevel then return end
    local now = os.clock()
    if now - state.lastCampBuild < state.campBuildInterval then return end
    state.lastCampBuild = now
    state.campBuildRunning = true

    pcall(function()
        local campground = getCampground()
        if not campground then return end

        for _, spec in ipairs(CAMP_BUILD_QUEUE) do
            if not state.autoFarm then break end
            if not campBuildIsDone(spec) then
                local item = findOwnedNamedItem(spec.name)
                if not item then
                    local woodCost, scrapCost = getCraftCost(spec.name)
                    if woodCost == nil or scrapCost == nil then return end
                    local totalWood = tonumber(campground:GetAttribute("TotalWood")) or 0
                    local totalScrap = tonumber(campground:GetAttribute("TotalScrap")) or 0
                    if totalWood < woodCost or totalScrap < scrapCost then return end

                    if not isLive(CraftItem) then refreshRemotes() end
                    if not isLive(CraftItem) then return end
                    local crafted, response = callUtilityRemote(CraftItem, 2, spec.name)
                    if not crafted or response == false then return end

                    local deadline = os.clock() + 3
                    repeat
                        task.wait(0.1)
                        if campBuildIsDone(spec) then return end
                        item = findOwnedNamedItem(spec.name)
                    until item or not state.autoFarm or os.clock() >= deadline
                end

                if item and item.Parent then
                    cancelFarmTween()
                    local character = getCharacter()
                    if character then
                        pcall(character.PivotTo, character, CFrame.new(CHILD_CAMP_DROP))
                    end
                    lockFarmCharacter()
                    task.wait(0.25)
                    if placeCampStructure(item, spec.offset) then
                        markCampBuildDone(spec.name)
                    end
                end
                -- One ordered craft/place step per service pass.
                return
            end
        end
    end)

    state.campBuildRunning = false
end

local function plantAvailableSaplings()
    if not state.active
        or not state.autoFarm
        or state.saplingServiceRunning
        or state.childRescueRunning then
        return
    end

    local now = os.clock()
    if now - state.lastSaplingPlant < state.saplingInterval then return end
    state.lastSaplingPlant = now
    state.saplingServiceRunning = true

    pcall(function()
        if not isLive(RequestPlantItem) then refreshRemotes() end
        if not isLive(RequestPlantItem) then return end
        local items = workspace:FindFirstChild("Items")
        if not items then return end

        local saplings = {}
        for _, item in ipairs(items:GetChildren()) do
            if item.Name == "Sapling" then
                table.insert(saplings, item)
            end
        end
        if #saplings == 0 then return end

        local firePart = getPart(getMainFire())
        local center = firePart and firePart.Position or Vector3.new(0, 10, 0)
        state.saplingRotation = (state.saplingRotation + math.rad(23)) % (math.pi * 2)

        for index, sapling in ipairs(saplings) do
            if not state.autoFarm then break end
            if sapling and sapling.Parent then
                -- Four staggered rings, all strictly inside the requested
                -- 100-stud campfire radius. The center is MainFire, never player.
                local radius = 40 + ((index - 1) % 4) * 18
                local angle = state.saplingRotation + (index - 1) * 2.399963229728653
                local x = center.X + math.cos(angle) * radius
                local z = center.Z + math.sin(angle) * radius
                local params = RaycastParams.new()
                params.FilterType = Enum.RaycastFilterType.Exclude
                local character = getCharacter()
                params.FilterDescendantsInstances = character and { character } or {}
                local hit = workspace:Raycast(
                    Vector3.new(x, center.Y + 120, z),
                    Vector3.new(0, -300, 0),
                    params
                )
                local position = Vector3.new(x, hit and hit.Position.Y or center.Y, z)
                callUtilityRemote(RequestPlantItem, 1.25, sapling, position)
                task.wait(0.05)
            end
        end
    end)

    state.saplingServiceRunning = false
end

task.spawn(function()
    while state.active do
        if state.autoFarm then
            plantAvailableSaplings()
            runCampBuildService()
            task.wait(0.5)
        else
            task.wait(1)
        end
    end
end)

'''
s = s.replace(insert_marker, automation + insert_marker, 1)

# When Auto Farm is disabled, make in-progress services stop advertising busy.
needle = '''    state.childRescuePending = false
    state.childRescueRunning = false

    cancelFarmTween()'''
if needle in s:
    s = s.replace(
        needle,
        '''    state.childRescuePending = false
    state.childRescueRunning = false
    state.saplingServiceRunning = false
    state.campBuildRunning = false

    cancelFarmTween()''',
        1,
    )

# Static invariants for this revision.
required = [
    'FARM_PATROL_Y = 60',
    'FARM_PLATFORM_Y = -54',
    'CHILD_CAMP_DROP = Vector3.new(0, 15, 0)',
    'SetGameplayPausedNotificationEnabled(false)',
    'RequestPlantItem',
    'CraftItem',
    'RequestPlaceStructure',
    'saplingInterval = 10',
    'strongAxePatrolSpeed = 80',
    'local CAMP_BUILD_QUEUE = {',
    'name = "Giant Bed"',
    'task.wait(2)',
    'task.wait(1)',
]
for token in required:
    if token not in s:
        raise RuntimeError(f'missing required token: {token}')

if 'math.cos(angle) * radius,\n            -50,' in s:
    raise RuntimeError('old under-map patrol point still present')
if 'platform.CFrame = CFrame.new(0, -53, 0)' in s:
    raise RuntimeError('old platform height still present')

path.write_text(s, encoding='utf-8')
print('patched', len(s), 'bytes')
