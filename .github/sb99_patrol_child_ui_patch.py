from pathlib import Path
import re

TARGET = Path('99 Nights Helper Godmode')
s = TARGET.read_text(encoding='utf-8')


def replace_once(old, new, label):
    global s
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly 1 match, got {count}')
    s = s.replace(old, new, 1)


def sub_once(pattern, repl, label, flags=0):
    global s
    s2, count = re.subn(pattern, repl, s, count=1, flags=flags)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly 1 regex match, got {count}')
    s = s2

# ---------------------------------------------------------------------------
# Remote + constants/state
# ---------------------------------------------------------------------------
replace_once(
    'local RequestTakeDiamonds = nil',
    'local RequestTakeDiamonds = nil\nlocal RequestBurnItem = nil',
    'RequestBurnItem declaration'
)
replace_once(
    '    RequestTakeDiamonds = findReplicated("RequestTakeDiamonds")',
    '    RequestTakeDiamonds = findReplicated("RequestTakeDiamonds")\n    RequestBurnItem = findReplicated("RequestBurnItem")',
    'RequestBurnItem refresh'
)
replace_once(
    '        or name == "RequestTakeDiamonds" then',
    '        or name == "RequestTakeDiamonds"\n        or name == "RequestBurnItem" then',
    'RequestBurnItem descendant refresh'
)
replace_once(
    'local FARM_PATROL_Y = 60',
    'local FARM_PATROL_Y = 30',
    'surface patrol height'
)
replace_once(
    '''    patrolRadius = 700,
    patrolSpeed = 60,
    strongAxePatrolSpeed = 80,
    patrolIndex = 1,

    saplingInterval = 10,
    lastSaplingPlant = 0,
    saplingRotation = 0,''',
    '''    patrolRadius = 300,
    patrolMinRadius = 300,
    patrolMaxRadius = 800,
    patrolSpeed = 38,
    strongAxePatrolSpeed = 52,
    patrolIndex = 1,
    patrolExploreIndex = 0,

    saplingInterval = 10,
    lastSaplingPlant = 0,
    saplingSlot = tonumber(G.SB99_SAPLING_SLOT) or 0,''',
    'patrol and sapling state'
)
replace_once(
    '    resourcePassLimit = 18,',
    '    resourcePassLimit = 64,',
    'resource throughput'
)
replace_once(
    'G.SB99_CAMP_BUILD_DONE = state.campBuildDone',
    'G.SB99_CAMP_BUILD_DONE = state.campBuildDone\nG.SB99_SAPLING_SLOT = state.saplingSlot',
    'persist sapling slot'
)

# ---------------------------------------------------------------------------
# Direct campfire burn path and higher-throughput smart resources.
# ---------------------------------------------------------------------------
resource_service = r'''local function burnItemIntoCampfire(item)
    if not item or not item.Parent then
        return false
    end

    local mainFire = getMainFire()
    if not mainFire then
        return false
    end

    if not isLive(RequestBurnItem) then
        refreshRemotes()
    end
    if not isLive(RequestBurnItem) then
        return false
    end

    if RequestBurnItem:IsA("RemoteEvent") then
        local ok = pcall(RequestBurnItem.FireServer, RequestBurnItem, mainFire, item)
        return ok
    end

    if RequestBurnItem:IsA("RemoteFunction") then
        local ok, response = callUtilityRemote(RequestBurnItem, 1.5, mainFire, item)
        return ok and response ~= false
    end

    return false
end

local function runResourceService()
    if not state.active
        or not state.smartResources
        or state.resourceServiceRunning
        or state.foodServiceRunning
        or state.childRescueRunning
        or state.strongholdControl then
        return
    end

    state.resourceServiceRunning = true
    pcall(function()
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

        local processed = 0
        local snapshot = items:GetChildren()
        for _, item in ipairs(snapshot) do
            if not state.active or not state.smartResources or state.strongholdControl then
                break
            end

            local cooldown = resourceCooldown[item]
            if item.Parent == items and (not cooldown or cooldown <= now) then
                local target = resourceTarget(item, campfireMaxed, fuelRatio)
                if target then
                    resourceCooldown[item] = now + 1.1
                    local handled = false

                    if target == CAMPFIRE_DROP then
                        -- RequestBurnItem is the authoritative fire path. Falling
                        -- back to dragging keeps compatibility if a server build
                        -- temporarily moves or replaces the remote.
                        handled = burnItemIntoCampfire(item)
                        if not handled and item.Parent == items then
                            handled = dragItemTo(item, CFrame.new(CAMPFIRE_DROP))
                        end
                    else
                        handled = dragItemTo(item, CFrame.new(target))
                    end

                    if handled then
                        processed = processed + 1
                        task.wait(0.02)

                        if target == CAMPFIRE_DROP then
                            task.wait(0.03)
                            local updatedLevel = getCampfireLevel()
                            if updatedLevel ~= nil and updatedLevel >= state.campfireTargetLevel then
                                campfireMaxed = true
                            end
                            fuelRatio = getCampfireFuelRatio()
                        end
                    end
                end
            end

            if processed >= state.resourcePassLimit then
                break
            end
        end
    end)
    state.resourceServiceRunning = false
end
'''
sub_once(
    r'local function runResourceService\(\).*?\nend\n\nlocal promptOriginals =',
    resource_service + '\nlocal promptOriginals =',
    'resource service rewrite',
    re.S
)

# ---------------------------------------------------------------------------
# Streaming-safe child rescue. Store each child immediately after streaming
# its area instead of discovering all positions first and retaining stale refs.
# ---------------------------------------------------------------------------
child_block = r'''local function getItemBag()
    return player:FindFirstChild("ItemBag")
end

local function getSackStoredCount(sack)
    if not sack then
        return 0
    end

    local count = tonumber(sack:GetAttribute("NumberItems"))
    if count ~= nil then
        return math.max(0, count)
    end

    return 0
end

local function isStorageBag(item)
    if not item or not item.Parent then
        return false
    end
    local capacity = tonumber(item:GetAttribute("Capacity"))
    local count = tonumber(item:GetAttribute("NumberItems"))
    return capacity ~= nil and count ~= nil and capacity > count
end

local function getRescueBags(requiredSlots)
    local bags = {}
    local seen = {}

    -- Current game scripts store baggable objects through Inventory bags first.
    local inventory = player:FindFirstChild("Inventory")
    local orderedContainers = {}
    if inventory then table.insert(orderedContainers, inventory) end
    for _, container in ipairs(ownedContainers()) do
        if container and container ~= inventory then
            table.insert(orderedContainers, container)
        end
    end

    for _, container in ipairs(orderedContainers) do
        for _, item in ipairs(container:GetChildren()) do
            if not seen[item] and isStorageBag(item) then
                seen[item] = true
                local capacity = tonumber(item:GetAttribute("Capacity")) or 0
                local count = tonumber(item:GetAttribute("NumberItems")) or 0
                table.insert(bags, {
                    item = item,
                    free = math.max(0, capacity - count),
                    preferred = isSack(item),
                })
            end
        end
    end

    table.sort(bags, function(a, b)
        local aFits = a.free >= requiredSlots
        local bFits = b.free >= requiredSlots
        if aFits ~= bFits then
            return aFits
        end
        if a.preferred ~= b.preferred then
            return a.preferred
        end
        return a.free > b.free
    end)

    return bags
end

local function chooseRescueSack(requiredSlots)
    local bags = getRescueBags(requiredSlots)
    local first = bags[1]
    return first and first.item or nil, first and first.free or 0
end

local function equipOwnedItem(item)
    if not item or not item.Parent then
        return false
    end
    if not isLive(EquipItemHandle) then
        refreshRemotes()
    end
    if not isLive(EquipItemHandle) then
        return false
    end

    local worked, response = callUtilityRemote(EquipItemHandle, 0.75, "FireAllClients", item)
    if worked and response ~= false then
        return true
    end
    worked, response = callUtilityRemote(EquipItemHandle, 0.75, item)
    return worked and response ~= false
end

local function focusCameraAt(position)
    local camera = workspace.CurrentCamera
    local root = getRoot()
    if camera and root then
        pcall(function()
            camera.CFrame = CFrame.lookAt(root.Position + Vector3.new(0, 3, 0), position)
        end)
    end
end

local function getMissingChildPositions()
    local map = workspace:FindFirstChild("Map")
    local missing = map and map:FindFirstChild("MissingKids")
    local result = {}
    if not missing then
        return result
    end

    for key, position in pairs(missing:GetAttributes()) do
        if typeof(position) == "Vector3" then
            table.insert(result, { key = tostring(key), position = position })
        end
    end
    table.sort(result, function(a, b)
        return a.key < b.key
    end)
    return result
end

local function reacquireChild(childName)
    local characters = workspace:FindFirstChild("Characters")
    if not characters then
        return nil
    end
    local exact = characters:FindFirstChild(childName)
    if exact and exact:IsA("Model") then
        return exact
    end
    return nil
end

local function childStoredInItemBag(childName)
    local itemBag = getItemBag()
    if not itemBag then
        return false
    end
    for _, object in ipairs(itemBag:GetDescendants()) do
        if object.Name == childName and isLostChild(object) then
            return true
        end
    end
    return false
end

local function storeChildInSack(sack, child)
    if not state.autoFarm
        or not state.autoChildRescue
        or state.strongholdControl
        or not sack
        or not sack.Parent
        or not child
        or not child.Parent then
        return false
    end

    local childName = child.Name
    local part = getPart(child)
    local character = getCharacter()
    if part and character then
        pcall(character.PivotTo, character, part.CFrame * CFrame.new(0, 0, 3))
        lockFarmCharacter()
        focusCameraAt(part.Position)
        task.wait(2)
    end

    -- Streaming can replace the model instance during the two-second wait.
    -- Always reacquire by the stable child name before invoking the server.
    child = reacquireChild(childName) or child
    if not child or not child.Parent then
        return false
    end

    if not isLive(RequestBagStoreItem) then
        refreshRemotes()
    end
    if not isLive(RequestBagStoreItem) then
        return false
    end

    local before = getSackStoredCount(sack)
    for attempt = 1, 3 do
        if not state.autoFarm or state.strongholdControl then
            return false
        end

        child = reacquireChild(childName) or child
        if not child or not child.Parent then
            return true
        end

        local ok, response = callUtilityRemote(RequestBagStoreItem, 1.5, sack, child)
        if ok and response ~= false then
            task.wait(0.15)
        end

        local after = getSackStoredCount(sack)
        local characters = workspace:FindFirstChild("Characters")
        local leftWorld = not child.Parent or (characters and not child:IsDescendantOf(characters))
        if after > before or leftWorld or childStoredInItemBag(childName) then
            state.childRescueObserved[childName] = true
            return true
        end

        -- Some executors/game builds require the child's prompt to be activated
        -- before the same authoritative bag remote accepts it.
        if attempt == 1 then
            local prompt = child:FindFirstChildWhichIsA("ProximityPrompt", true)
            if prompt then
                firePromptNow(prompt)
                task.wait(0.15)
            end
        end
        task.wait(0.2)
    end

    return false
end

local function getBaggedChildren()
    local result = {}
    local itemBag = getItemBag()
    if not itemBag then
        return result
    end
    for _, object in ipairs(itemBag:GetDescendants()) do
        if isLostChild(object) then
            table.insert(result, object)
        end
    end
    return result
end

local function dropChildrenAtCamp(usedBags)
    local character = getCharacter()
    if character then
        pcall(character.PivotTo, character, CFrame.new(CHILD_CAMP_DROP))
    end
    lockFarmCharacter()
    focusCameraAt(CHILD_CAMP_DROP)
    task.wait(0.5)

    if not isLive(RequestBagDropItem) then
        refreshRemotes()
    end
    if not isLive(RequestBagDropItem) then
        return false
    end

    local bags = {}
    for bag in pairs(usedBags) do
        if bag and bag.Parent then
            table.insert(bags, bag)
        end
    end
    for _, info in ipairs(getRescueBags(0)) do
        if info.item and info.item.Parent and not usedBags[info.item] then
            table.insert(bags, info.item)
        end
    end

    local droppedAny = false
    local bagged = getBaggedChildren()
    for _, child in ipairs(bagged) do
        if not state.autoFarm or state.strongholdControl then
            break
        end
        local childName = child.Name
        for _, bag in ipairs(bags) do
            if bag.Parent and child.Parent then
                local before = getSackStoredCount(bag)
                local oldParent = child.Parent
                local ok, response = callUtilityRemote(RequestBagDropItem, 1.25, bag, child)
                if ok and response ~= false then
                    task.wait(0.18)
                    local after = getSackStoredCount(bag)
                    if not child.Parent or child.Parent ~= oldParent or after < before then
                        state.childRescueVerified[childName] = true
                        droppedAny = true
                        break
                    end
                end
            end
        end
    end

    task.wait(1)
    getUnrescuedChildren()
    return droppedAny
end

local function runChildRescueAttempt()
    if not state.autoFarm
        or not state.autoChildRescue
        or state.strongholdControl
        or state.childRescueRunning
        or state.childRescueCompleted
        or state.childRescueAttempts >= state.childRescueMaxAttempts then
        return false
    end

    local level = getCampfireLevel()
    if level == nil or level < state.campfireTargetLevel then
        return false
    end

    state.childRescueRunning = true
    state.childRescuePending = false
    state.childRescueAttempts = state.childRescueAttempts + 1
    cancelFarmTween()

    local camera = workspace.CurrentCamera
    local oldCameraType = camera and camera.CameraType
    local oldCameraSubject = camera and camera.CameraSubject
    local oldCameraCFrame = camera and camera.CFrame
    if camera then
        pcall(function()
            camera.CameraType = Enum.CameraType.Scriptable
        end)
    end

    local usedBags = {}
    local storedNames = {}
    local success = false

    pcall(function()
        local function storeCurrentlyLoaded()
            local loaded = getUnrescuedChildren()
            for _, child in ipairs(loaded) do
                if not state.autoFarm or state.strongholdControl then
                    break
                end
                if not storedNames[child.Name] and not state.childRescueVerified[child.Name] then
                    local bag = chooseRescueSack(1)
                    if bag and storeChildInSack(bag, child) then
                        usedBags[bag] = true
                        storedNames[child.Name] = true
                        task.wait(1)
                    end
                end
            end
        end

        -- Grab any already-streamed child first.
        storeCurrentlyLoaded()

        -- Then visit each MissingKids position and immediately bag whatever
        -- child streams in there. This avoids stale references across regions.
        for _, entry in ipairs(getMissingChildPositions()) do
            if not state.autoFarm or state.strongholdControl then
                break
            end
            if verifiedChildCount() + (function()
                local n = 0
                for _ in pairs(storedNames) do n = n + 1 end
                return n
            end)() >= 4 then
                break
            end

            local character = getCharacter()
            if character then
                pcall(character.PivotTo, character, CFrame.new(entry.position + Vector3.new(0, 3, 0)))
                lockFarmCharacter()
                focusCameraAt(entry.position)
                task.wait(2)
                storeCurrentlyLoaded()
            end
        end

        if next(usedBags) ~= nil then
            dropChildrenAtCamp(usedBags)
        end

        task.wait(1)
        getUnrescuedChildren()
        success = verifiedChildCount() >= 4
    end)

    if camera then
        pcall(function()
            if oldCameraCFrame then camera.CFrame = oldCameraCFrame end
            if oldCameraSubject then camera.CameraSubject = oldCameraSubject end
            camera.CameraType = oldCameraType or Enum.CameraType.Custom
        end)
    end

    state.childRescueRunning = false
    state.childRescuePending = false
    if success then
        state.childRescueCompleted = true
        state.nextChildRescueAt = 0
    else
        state.nextChildRescueAt = os.clock() + 5
    end

    -- Stay at the camp after dropping children. The daytime patrol controller
    -- will take over from here; do not unnecessarily send the player under map.
    return success
end

'''
sub_once(
    r'local function getItemBag\(\).*?\nlocal function moveFarmTo\(position, ignoreInterrupts\)',
    child_block + 'local function moveFarmTo(position, ignoreInterrupts)',
    'streaming-safe child rescue rewrite',
    re.S
)

# ---------------------------------------------------------------------------
# Sapling circle: one deterministic ring, persisted slot, all available saplings
# every 10 seconds.
# ---------------------------------------------------------------------------
sapling_func = r'''local function plantAvailableSaplings()
    if not state.active
        or not state.autoFarm
        or not state.autoPlant
        or state.saplingServiceRunning
        or state.childRescueRunning
        or state.strongholdControl then
        return
    end

    local now = os.clock()
    if now - state.lastSaplingPlant < state.saplingInterval then
        return
    end
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
        local radius = 82
        local slots = 48

        -- A real geometric ring: every slot has the same radius. Persist the
        -- last successful slot so later batches continue instead of starting
        -- over and stacking saplings on the same positions.
        for _, sapling in ipairs(saplings) do
            if not state.autoFarm or state.strongholdControl then break end
            if sapling and sapling.Parent == items then
                local slot = (state.saplingSlot % slots) + 1
                local angle = ((slot - 1) / slots) * math.pi * 2
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

                local ok, response = callUtilityRemote(RequestPlantItem, 1.25, sapling, position)
                if ok and response ~= false then
                    state.saplingSlot = slot
                    G.SB99_SAPLING_SLOT = slot
                end
                task.wait(0.045)
            end
        end
    end)

    state.saplingServiceRunning = false
end
'''
sub_once(
    r'local function plantAvailableSaplings\(\).*?\nend\n\ntask\.spawn\(function\(\)\n    while state\.active do\n        if state\.autoFarm then\n            plantAvailableSaplings\(\)',
    sapling_func + '\n\ntask.spawn(function()\n    while state.active do\n        if state.autoFarm then\n            plantAvailableSaplings()',
    'sapling circle rewrite',
    re.S
)

# ---------------------------------------------------------------------------
# Dynamic map-aware patrol: Level 1 radius 300 -> Level 6 radius 800. Prefer
# Small Tree targets and use deterministic exploration points when no tree is
# currently streamed, so daytime still reveals chests/items/enemies/map.
# ---------------------------------------------------------------------------
patrol_block = r'''local treeVisitCooldown = setmetatable({}, { __mode = "k" })

local function getFarmCenter()
    local firePart = getPart(getMainFire())
    local center = firePart and firePart.Position or Vector3.new(0, 10, 0)
    return Vector3.new(center.X, FARM_PATROL_Y, center.Z)
end

local function currentFarmRadius()
    local level = math.clamp(tonumber(getCampfireLevel()) or 1, 1, state.campfireTargetLevel)
    if state.campfireTargetLevel <= 1 then
        return state.patrolMaxRadius
    end
    local alpha = (level - 1) / (state.campfireTargetLevel - 1)
    return math.floor(state.patrolMinRadius + (state.patrolMaxRadius - state.patrolMinRadius) * alpha + 0.5)
end

local function smallTreeAvailable(tree)
    if not tree or not tree.Parent or tree.Name ~= "Small Tree" then
        return false
    end
    local health = tonumber(tree:GetAttribute("Health"))
    return health == nil or health > 0
end

local function chooseSmallTreeTarget()
    local root = getRoot()
    if not root then return nil, nil end

    local center = getFarmCenter()
    local radius = currentFarmRadius()
    local now = os.clock()
    local bestTree = nil
    local bestDistance = math.huge

    for _, tree in ipairs(treeCache) do
        if smallTreeAvailable(tree) then
            local part = getPart(tree)
            if part then
                local dxCenter = part.Position.X - center.X
                local dzCenter = part.Position.Z - center.Z
                local fromCenter = math.sqrt(dxCenter * dxCenter + dzCenter * dzCenter)
                local cooldown = treeVisitCooldown[tree]
                if fromCenter <= radius and (not cooldown or cooldown <= now) then
                    local dx = part.Position.X - root.Position.X
                    local dz = part.Position.Z - root.Position.Z
                    local distance = math.sqrt(dx * dx + dz * dz)
                    if distance < bestDistance then
                        bestTree = tree
                        bestDistance = distance
                    end
                end
            end
        end
    end

    if bestTree then
        local part = getPart(bestTree)
        treeVisitCooldown[bestTree] = now + 4
        return Vector3.new(part.Position.X, FARM_PATROL_Y, part.Position.Z), bestTree
    end
    return nil, nil
end

local function nextExploreTarget()
    local center = getFarmCenter()
    local radius = currentFarmRadius()
    state.patrolExploreIndex = state.patrolExploreIndex + 1

    -- Two interleaved deterministic rings provide full-map coverage without
    -- random wandering. As the campfire upgrades, the same pattern expands
    -- smoothly from 300 to 800 studs.
    local index = state.patrolExploreIndex - 1
    local pointsPerRing = 16
    local ring = math.floor(index / pointsPerRing) % 2
    local point = index % pointsPerRing
    local ringScale = ring == 0 and 0.62 or 0.95
    local offset = ring == 0 and 0 or (math.pi / pointsPerRing)
    local angle = (point / pointsPerRing) * math.pi * 2 + offset
    local r = radius * ringScale

    return Vector3.new(
        center.X + math.cos(angle) * r,
        FARM_PATROL_Y,
        center.Z + math.sin(angle) * r
    )
end

local function nextDayFarmTarget()
    local treePoint, tree = chooseSmallTreeTarget()
    if treePoint then
        return treePoint, tree
    end
    return nextExploreTarget(), nil
end

'''
sub_once(
    r'local patrolPoints = \{\}.*?\nlocal function enableFarm\(\)',
    patrol_block + 'local function enableFarm()',
    'dynamic patrol rewrite',
    re.S
)

# Reset dynamic traversal state each time Auto Farm is enabled.
replace_once(
    '''    state.diamondFarm = true
    state.patrolIndex = 1
    state.childRescueAttempts = 0''',
    '''    state.diamondFarm = true
    state.patrolIndex = 1
    state.patrolExploreIndex = 0
    table.clear(treeVisitCooldown)
    state.childRescueAttempts = 0''',
    'farm restart traversal state'
)

# Main daytime controller: continuously visit Small Trees, otherwise explore
# current unlocked radius. Never return home after an arbitrary fixed sweep.
old_patrol_controller = '''                else
                    local point = patrolPoints[state.patrolIndex]

                    if moveFarmTo(point, false) then
                        state.patrolIndex = state.patrolIndex + 1

                        -- After a complete sweep, return home before starting again.
                        if state.patrolIndex > #patrolPoints then
                            state.patrolIndex = 1
                            moveFarmTo(FARM_HOME, true)
                            task.wait(1)
                        else
                            task.wait(0.3)
                        end
                    else
                        task.wait(0.1)
                    end
                end'''
new_patrol_controller = '''                else
                    local point, tree = nextDayFarmTarget()
                    if point and moveFarmTo(point, false) then
                        -- Brief dwell gives Auto Chop/Kill Aura/chest prompting
                        -- time to act while keeping daytime traversal continuous.
                        task.wait(tree and 0.55 or 0.25)
                    else
                        task.wait(0.1)
                    end
                end'''
replace_once(old_patrol_controller, new_patrol_controller, 'daytime tree patrol controller')

# ---------------------------------------------------------------------------
# Compact phone UI. Remove low-value info rows, keep two useful collapsible
# sections, restart one-shot/retry state when a manual toggle is re-enabled.
# ---------------------------------------------------------------------------
ui_anchor = 'task.defer(function()\n--==============================================================\n-- RESPONSIVE COLLAPSIBLE UI\n--=============================================================='
idx = s.find(ui_anchor)
if idx < 0:
    raise RuntimeError('UI tail anchor missing')

ui = r'''task.defer(function()
--==============================================================
-- PHONE-FIRST COLLAPSIBLE UI
--==============================================================

local screen = Instance.new("ScreenGui")
screen.Name = "SB99_RedTeamUI"
screen.ResetOnSpawn = false
screen.DisplayOrder = 999999
screen.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
screen.IgnoreGuiInset = false
screen.Parent = playerGui

local frame = Instance.new("Frame")
frame.Name = "Main"
frame.Size = UDim2.fromOffset(286, 430)
frame.Position = UDim2.new(0.5, -143, 0, 6)
frame.BackgroundColor3 = Color3.fromRGB(18, 18, 22)
frame.BorderSizePixel = 0
frame.Active = true
frame.Parent = screen

local function rounded(instance, radius)
    local corner = Instance.new("UICorner")
    corner.CornerRadius = UDim.new(0, radius or 8)
    corner.Parent = instance
end
rounded(frame, 12)

local stroke = Instance.new("UIStroke")
stroke.Color = Color3.fromRGB(72, 72, 84)
stroke.Thickness = 1
stroke.Parent = frame

local uiScale = Instance.new("UIScale")
uiScale.Scale = 1
uiScale.Parent = frame

local header = Instance.new("Frame")
header.Size = UDim2.new(1, 0, 0, 38)
header.BackgroundColor3 = Color3.fromRGB(29, 29, 35)
header.BorderSizePixel = 0
header.Active = true
header.Parent = frame
rounded(header, 12)

local title = Instance.new("TextLabel")
title.Size = UDim2.new(1, -48, 1, 0)
title.Position = UDim2.fromOffset(10, 0)
title.BackgroundTransparency = 1
title.Text = "Smile B | 99 Nights"
title.TextColor3 = Color3.new(1, 1, 1)
title.TextXAlignment = Enum.TextXAlignment.Left
title.Font = Enum.Font.GothamBold
title.TextSize = 12
title.Parent = header

local minimize = Instance.new("TextButton")
minimize.Size = UDim2.fromOffset(30, 26)
minimize.Position = UDim2.new(1, -36, 0, 6)
minimize.BackgroundColor3 = Color3.fromRGB(48, 48, 57)
minimize.BorderSizePixel = 0
minimize.Text = "-"
minimize.TextColor3 = Color3.new(1, 1, 1)
minimize.Font = Enum.Font.GothamBold
minimize.TextSize = 16
minimize.Parent = header
rounded(minimize, 7)

local status = Instance.new("TextLabel")
status.Size = UDim2.new(1, -12, 0, 38)
status.Position = UDim2.fromOffset(6, 43)
status.BackgroundColor3 = Color3.fromRGB(27, 27, 33)
status.BorderSizePixel = 0
status.TextColor3 = Color3.fromRGB(215, 215, 225)
status.Font = Enum.Font.Gotham
status.TextSize = 9
status.TextWrapped = true
status.Parent = frame
rounded(status, 8)

local scroll = Instance.new("ScrollingFrame")
scroll.Size = UDim2.new(1, -12, 1, -90)
scroll.Position = UDim2.fromOffset(6, 85)
scroll.BackgroundTransparency = 1
scroll.BorderSizePixel = 0
scroll.ScrollBarThickness = 3
scroll.CanvasSize = UDim2.new()
scroll.AutomaticCanvasSize = Enum.AutomaticSize.Y
scroll.ScrollingDirection = Enum.ScrollingDirection.Y
scroll.Parent = frame

local rootLayout = Instance.new("UIListLayout")
rootLayout.Padding = UDim.new(0, 5)
rootLayout.SortOrder = Enum.SortOrder.LayoutOrder
rootLayout.Parent = scroll

local refreshers = {}

local function refreshAll()
    for _, fn in ipairs(refreshers) do
        pcall(fn)
    end
end

local function makeSection(label, openByDefault)
    local holder = Instance.new("Frame")
    holder.Size = UDim2.new(1, -2, 0, 36)
    holder.AutomaticSize = Enum.AutomaticSize.Y
    holder.BackgroundColor3 = Color3.fromRGB(24, 24, 30)
    holder.BorderSizePixel = 0
    holder.Parent = scroll
    rounded(holder, 8)

    local layout = Instance.new("UIListLayout")
    layout.Padding = UDim.new(0, 4)
    layout.Parent = holder

    local open = openByDefault ~= false
    local head = Instance.new("TextButton")
    head.Size = UDim2.new(1, 0, 0, 34)
    head.BackgroundColor3 = Color3.fromRGB(35, 35, 43)
    head.BorderSizePixel = 0
    head.TextColor3 = Color3.fromRGB(232, 232, 238)
    head.Font = Enum.Font.GothamBold
    head.TextSize = 10
    head.TextXAlignment = Enum.TextXAlignment.Left
    head.Parent = holder
    rounded(head, 8)

    local content = Instance.new("Frame")
    content.Size = UDim2.new(1, 0, 0, 0)
    content.AutomaticSize = Enum.AutomaticSize.Y
    content.BackgroundTransparency = 1
    content.Parent = holder
    local list = Instance.new("UIListLayout")
    list.Padding = UDim.new(0, 4)
    list.Parent = content

    local function render()
        content.Visible = open
        content.AutomaticSize = open and Enum.AutomaticSize.Y or Enum.AutomaticSize.None
        content.Size = UDim2.new(1, 0, 0, 0)
        head.Text = (open and "  v  " or "  >  ") .. label
    end
    render()
    track(head.MouseButton1Click:Connect(function()
        open = not open
        render()
    end))
    return content
end

local function makeToggle(parent, label, getter, setter, farmLocked)
    local button = Instance.new("TextButton")
    button.Size = UDim2.new(1, 0, 0, 32)
    button.BorderSizePixel = 0
    button.TextColor3 = Color3.new(1, 1, 1)
    button.Font = Enum.Font.GothamBold
    button.TextSize = 9
    button.TextXAlignment = Enum.TextXAlignment.Left
    button.Parent = parent
    rounded(button, 7)

    local function render()
        local enabled = getter() == true
        local locked = farmLocked and state.autoFarm
        button.BackgroundColor3 = enabled and Color3.fromRGB(28, 112, 61) or Color3.fromRGB(47, 47, 56)
        button.Text = "   " .. (locked and "[LOCK] " or "") .. label .. (enabled and "  ON" or "  OFF")
    end
    table.insert(refreshers, render)

    track(button.MouseButton1Click:Connect(function()
        if farmLocked and state.autoFarm then return end
        setter(not getter())
        refreshAll()
    end))
end

local farmSection = makeSection("AUTO FARM", true)
makeToggle(farmSection, "Auto Farm - full suite", function() return state.autoFarm end, function(v)
    if v then enableFarm() else disableFarm() end
end, false)
makeToggle(farmSection, "Auto Chop", function() return state.autoChop end, function(v)
    state.autoChop = v
    if v then table.clear(attackCooldown); table.clear(treeVisitCooldown) end
end, true)
makeToggle(farmSection, "Kill Aura", function() return state.killAura end, function(v)
    state.killAura = v
    if v then table.clear(attackCooldown) end
end, true)
makeToggle(farmSection, "Auto Best Gear", function() return state.autoBestGear end, function(v)
    state.autoBestGear = v
    if v then table.clear(gearCooldown) end
end, true)
makeToggle(farmSection, "Smart Fire / Scrap", function() return state.smartResources end, function(v)
    state.smartResources = v
    if v then table.clear(resourceCooldown); state.resourceServiceRunning = false end
end, true)
makeToggle(farmSection, "Open Chests", function() return state.autoChest end, function(v)
    state.autoChest = v
    if v then table.clear(promptCooldown) end
end, true)
makeToggle(farmSection, "Plant Sapling Circle", function() return state.autoPlant end, function(v)
    state.autoPlant = v
    if v then state.lastSaplingPlant = 0; state.saplingServiceRunning = false end
end, true)
makeToggle(farmSection, "Bench + Beds", function() return state.autoCampBuild end, function(v)
    state.autoCampBuild = v
    if v then state.lastCampBuild = 0; state.campBuildRunning = false end
end, true)
makeToggle(farmSection, "Rescue 4 Children", function() return state.autoChildRescue end, function(v)
    state.autoChildRescue = v
    state.childRescueRunning = false
    state.childRescuePending = false
    if v then
        state.childRescueAttempts = 0
        state.childRescueCompleted = false
        state.childRescueObserved = {}
        state.childRescueVerified = {}
        state.nextChildRescueAt = 0
    end
end, true)

local strongholdSection = makeSection("STRONGHOLD", false)
makeToggle(strongholdSection, "Diamond Farm", function() return state.diamondFarm end, function(v)
    state.diamondFarm = v
    state.strongholdControl = false
    state.strongholdRunning = false
    state.strongholdBaseline = nil
    state.strongholdRetryAt = 0
    state.strongholdCycleComplete = false
    state.strongholdStatus = v and "Waiting" or "Off"
end, true)

local ball = Instance.new("TextButton")
ball.Name = "SB_Ball"
ball.Size = UDim2.fromOffset(50, 50)
ball.Position = UDim2.new(0, 14, 0.5, -25)
ball.BackgroundColor3 = Color3.fromRGB(24, 24, 29)
ball.BorderSizePixel = 0
ball.Text = "SB"
ball.TextColor3 = Color3.new(1, 1, 1)
ball.Font = Enum.Font.GothamBold
ball.TextSize = 16
ball.Visible = false
ball.Active = true
ball.Parent = screen
rounded(ball, 25)

local function clampToViewport(position, size)
    local camera = workspace.CurrentCamera
    local viewport = camera and camera.ViewportSize or Vector2.new(1280, 720)
    return Vector2.new(
        math.clamp(position.X, 0, math.max(0, viewport.X - size.X)),
        math.clamp(position.Y, 0, math.max(0, viewport.Y - size.Y))
    )
end

local lastViewport = Vector2.zero
local function refreshResponsiveLayout()
    local camera = workspace.CurrentCamera
    if not camera then return end
    local viewport = camera.ViewportSize
    if viewport ~= lastViewport then
        lastViewport = viewport
        local widthScale = (viewport.X - 8) / 286
        local heightScale = (viewport.Y - 8) / 430
        uiScale.Scale = math.clamp(math.min(1, widthScale, heightScale), 0.76, 1)
        task.defer(function()
            if frame.Visible then
                local p = clampToViewport(frame.AbsolutePosition, frame.AbsoluteSize)
                frame.Position = UDim2.fromOffset(p.X, p.Y)
            elseif ball.Visible then
                local p = clampToViewport(ball.AbsolutePosition, ball.AbsoluteSize)
                ball.Position = UDim2.fromOffset(p.X, p.Y)
            end
        end)
    end
end

local function minimizeUI()
    local p = clampToViewport(frame.AbsolutePosition, ball.AbsoluteSize)
    ball.Position = UDim2.fromOffset(p.X, p.Y)
    frame.Visible = false
    ball.Visible = true
end
local function restoreUI()
    local p = clampToViewport(ball.AbsolutePosition, frame.AbsoluteSize)
    frame.Position = UDim2.fromOffset(p.X, p.Y)
    ball.Visible = false
    frame.Visible = true
end
track(minimize.MouseButton1Click:Connect(minimizeUI))

local dragging, dragInput, dragTouch, dragStart, frameStart = false, nil, nil, nil, nil
track(header.InputBegan:Connect(function(input)
    if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
        dragging = true
        dragStart = input.Position
        frameStart = frame.Position
        dragTouch = input.UserInputType == Enum.UserInputType.Touch and input or nil
        if dragTouch then dragInput = input end
    end
end))
track(header.InputChanged:Connect(function(input)
    if dragging and (input.UserInputType == Enum.UserInputType.MouseMovement or (dragTouch and input == dragTouch)) then
        dragInput = input
    end
end))
track(UserInputService.InputChanged:Connect(function(input)
    if dragging and input == dragInput and dragStart and frameStart then
        local delta = input.Position - dragStart
        local camera = workspace.CurrentCamera
        local viewport = camera and camera.ViewportSize or Vector2.zero
        local desired = Vector2.new(
            frameStart.X.Offset + delta.X + frameStart.X.Scale * viewport.X,
            frameStart.Y.Offset + delta.Y + frameStart.Y.Scale * viewport.Y
        )
        local p = clampToViewport(desired, frame.AbsoluteSize)
        frame.Position = UDim2.fromOffset(p.X, p.Y)
    end
end))
track(UserInputService.InputEnded:Connect(function(input)
    local owner = dragging and ((dragTouch and input == dragTouch) or (not dragTouch and input.UserInputType == Enum.UserInputType.MouseButton1))
    if owner then
        dragging, dragInput, dragTouch, dragStart, frameStart = false, nil, nil, nil, nil
    end
end))

local ballDragging, ballInput, ballTouch, ballStart, ballPos, ballMoved = false, nil, nil, nil, nil, false
track(ball.InputBegan:Connect(function(input)
    if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
        ballDragging = true
        ballMoved = false
        ballStart = input.Position
        ballPos = ball.Position
        ballTouch = input.UserInputType == Enum.UserInputType.Touch and input or nil
        if ballTouch then ballInput = input end
    end
end))
track(ball.InputChanged:Connect(function(input)
    if ballDragging and (input.UserInputType == Enum.UserInputType.MouseMovement or (ballTouch and input == ballTouch)) then
        ballInput = input
    end
end))
track(UserInputService.InputChanged:Connect(function(input)
    if not ballDragging or input ~= ballInput or not ballStart or not ballPos then return end
    local delta = input.Position - ballStart
    if delta.Magnitude > 6 then ballMoved = true end
    local camera = workspace.CurrentCamera
    local viewport = camera and camera.ViewportSize or Vector2.zero
    local desired = Vector2.new(
        ballPos.X.Offset + delta.X + ballPos.X.Scale * viewport.X,
        ballPos.Y.Offset + delta.Y + ballPos.Y.Scale * viewport.Y
    )
    local p = clampToViewport(desired, ball.AbsoluteSize)
    ball.Position = UDim2.fromOffset(p.X, p.Y)
end))
track(UserInputService.InputEnded:Connect(function(input)
    local owner = ballDragging and ((ballTouch and input == ballTouch) or (not ballTouch and input.UserInputType == Enum.UserInputType.MouseButton1))
    if not owner then return end
    ballDragging, ballInput, ballTouch = false, nil, nil
    if not ballMoved and ball.Visible then restoreUI() end
end))

task.spawn(function()
    while state.active do
        local fireLevel = getCampfireLevel()
        local diamonds = state.readDiamondCount and state.readDiamondCount() or nil
        local radius = currentFarmRadius()
        status.Text = string.format(
            "Godmode ON | Fire %s/6 | Radius %d\n%s | Diamonds %s",
            fireLevel and tostring(fireLevel) or "?",
            radius,
            tostring(state.strongholdStatus or "Off"),
            diamonds and tostring(diamonds) or "--"
        )
        refreshAll()
        refreshResponsiveLayout()
        task.wait(0.4)
    end
end)

task.defer(function()
    refreshAll()
    refreshResponsiveLayout()
end)

end)'''

s = s[:idx] + ui + '\n'

# Static invariants specific to this revision.
required = [
    'local FARM_PATROL_Y = 30',
    'RequestBurnItem = findReplicated("RequestBurnItem")',
    'local function currentFarmRadius()',
    'tree.Name ~= "Small Tree"',
    'local function getMissingChildPositions()',
    'child = reacquireChild(childName) or child',
    'local radius = 82',
    'G.SB99_SAPLING_SLOT = slot',
    '-- PHONE-FIRST COLLAPSIBLE UI',
]
for needle in required:
    if needle not in s:
        raise RuntimeError(f'missing invariant: {needle}')

if 'local FARM_PATROL_Y = 60' in s:
    raise RuntimeError('old patrol height remains')
if 'local point = patrolPoints[state.patrolIndex]' in s:
    raise RuntimeError('old fixed patrol controller remains')
if 'local infoSection = makeSection("INFO"' in s:
    raise RuntimeError('old info UI remains')

TARGET.write_text(s, encoding='utf-8')
print('patched bytes', len(s.encode('utf-8')))
