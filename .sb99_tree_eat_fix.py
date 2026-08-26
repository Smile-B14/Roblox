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

# More room for the full 800-stud map diameter, and enough throughput to use
# coal/canisters/oil/logs quickly while leveling the fire.
replace_once(
'''    resourcePassLimit = 8,
    resourcePickupRange = 220,
    resourcePauseUntil = 0,''',
'''    resourcePassLimit = 24,
    resourcePickupRange = 2000,
    resourcePauseUntil = 0,''',
'resource throughput')

# Expand explicit fuel aliases while still keeping attribute-based fuel support.
replace_once(
'''    ["oil barrel"] = true,
    ["biofuel"] = true,
    ["chair"] = true,''',
'''    ["oil barrel"] = true,
    ["biofuel"] = true,
    ["charcoal"] = true,
    ["gas canister"] = true,
    ["gasoline"] = true,
    ["propane tank"] = true,
    ["kerosene"] = true,
    ["firewood"] = true,
    ["chair"] = true,''',
'fuel aliases')

# Give drag ownership/replication a real mobile-friendly window. This affects
# logs/scrap, world food and gear pickup in the same safer direction.
replace_once('''        task.wait(0.08)
        if not item.Parent then''', '''        task.wait(0.15)
        if not item.Parent then''', 'drag ownership delay')
replace_once('''        task.wait(0.12)
        finishDrag()
        return item.Parent ~= nil''', '''        task.wait(0.30)
        finishDrag()
        task.wait(0.06)
        return item.Parent ~= nil''', 'drag replication delay')

# Auto Eat: use the direct RequestConsumeItem protocol. Inventory food is
# consumed directly. World cooked food is first brought beside the character,
# matching current live implementations, then consumed directly. Do not put
# one timeout into the generic 8-second RemoteFunction cooldown path.
regex_once(
r'''local function consumeFood\(item\).*?\nend\n\nlocal function requestEmergencyFoodRun\(\)''',
r'''local function directConsumeRequest(item)
    if not item or not item.Parent then
        return false, nil
    end

    if not isLive(RequestConsumeItem) then
        refreshRemotes()
    end
    local remote = RequestConsumeItem
    if not isLive(remote) then
        return false, nil
    end

    if remote:IsA("RemoteEvent") then
        local ok = pcall(remote.FireServer, remote, item)
        return ok, ok and true or nil
    end
    if not remote:IsA("RemoteFunction") then
        return false, nil
    end

    local done = false
    local ok = false
    local response = nil
    local thread = task.spawn(function()
        ok, response = pcall(remote.InvokeServer, remote, item)
        done = true
    end)

    local deadline = os.clock() + 2
    while state.active and not done and item.Parent and os.clock() < deadline do
        task.wait()
    end

    -- Item removal is the strongest confirmation even if the RemoteFunction
    -- response arrives late on a high-ping executor/mobile client.
    if not item.Parent then
        if not done and type(task.cancel) == "function" then
            pcall(task.cancel, thread)
        end
        return true, true
    end

    if not done then
        if type(task.cancel) == "function" then
            pcall(task.cancel, thread)
        end
        return false, nil
    end

    return ok, response
end

local function consumeFood(item)
    if not item or not item.Parent or not state.active then
        return false
    end

    local before = getRealHunger()
    local root = getRoot()
    if not root then
        return false
    end

    -- Current live scripts bring world cooked food beside the player before
    -- RequestConsumeItem, but inventory/backpack food can be consumed directly.
    if item:IsDescendantOf(workspace) then
        local part = getPart(item)
        if part and (part.Position - root.Position).Magnitude > 10 then
            dragItemTo(item, root.CFrame * CFrame.new(0, 2, -2))
            task.wait(0.12)
        end
    end

    local success, response = directConsumeRequest(item)
    if not success and item.Parent and item:IsDescendantOf(workspace) then
        -- One fresh drag/retry covers ownership races without poisoning future
        -- consume attempts with a long global cooldown.
        local liveRoot = getRoot()
        if liveRoot then
            dragItemTo(item, liveRoot.CFrame * CFrame.new(0, 2, -2))
            task.wait(0.15)
            success, response = directConsumeRequest(item)
        end
    end

    local explicitSuccess = success and (
        response == true
        or (type(response) == "table" and response.Success == true)
    )
    if explicitSuccess then
        return true
    end

    local verifyDeadline = os.clock() + 0.9
    repeat
        task.wait(0.05)
        local after = getRealHunger()
        if not item.Parent or (before ~= nil and after ~= nil and after > before) then
            return true
        end
    until not state.active or os.clock() >= verifyDeadline

    if item.Parent then
        failedFoodUntil[item] = os.clock() + 0.75
    end
    return false
end

local function requestEmergencyFoodRun()''',
'auto eat direct remote')

# Direct burn is the preferred path for every fuel while the fire is below 6.
# Verify server acceptance, then fall back to the physical drag protocol and
# retry the direct burn beside MainFire if necessary.
regex_once(
r'''local function burnItemIntoCampfire\(item\).*?\nend\n\nlocal function routeItemToScrapper\(item\)''',
r'''local function burnItemIntoCampfire(item)
    if not item or not item.Parent then return false end
    local fire = getMainFire()
    if not fire then return false end

    local beforeFuel = tonumber(fire:GetAttribute("FuelRemaining")) or 0
    local beforeLevel = getCampfireLevel() or tonumber(state.fireDerivedLevel) or 1

    local function accepted()
        if not item.Parent then
            return true
        end
        local liveFire = getMainFire()
        if not liveFire then
            return false
        end
        local afterFuel = tonumber(liveFire:GetAttribute("FuelRemaining")) or 0
        local afterLevel = getCampfireLevel() or beforeLevel
        return afterFuel > beforeFuel + 0.001 or afterLevel > beforeLevel
    end

    local function requestBurn()
        if not isLive(RequestBurnItem) then
            refreshRemotes()
        end
        local remote = RequestBurnItem
        if not isLive(remote) then
            return false
        end
        if remote:IsA("RemoteEvent") then
            return pcall(remote.FireServer, remote, fire, item)
        elseif remote:IsA("RemoteFunction") then
            local ok, response = callUtilityRemote(remote, 1.5, fire, item)
            return ok and response ~= false
        end
        return false
    end

    -- This RemoteEvent is accepted from anywhere by current live scripts and
    -- is much more reliable for leveling than waiting for the roaming player.
    if requestBurn() then
        local deadline = os.clock() + 0.9
        repeat
            task.wait(0.06)
            if accepted() then return true end
        until not state.active or os.clock() >= deadline
    end

    if not item.Parent then
        return true
    end

    local dropCF = getPhysicalFireDrop()
    if not dragItemTo(item, dropCF) and item.Parent then
        return false
    end
    task.wait(0.10)

    if item.Parent then
        requestBurn()
    end

    local deadline = os.clock() + 1.6
    repeat
        task.wait(0.08)
        if accepted() then return true end
    until not state.active or os.clock() >= deadline

    return not item.Parent
end

local function routeItemToScrapper(item)''',
'direct fire fueling')

# Scrapper routing gets one verified retry instead of abandoning the whole
# Smart Resources batch after a transient ownership/replication race.
regex_once(
r'''local function routeItemToScrapper\(item\).*?\nend\n\nlocal function runResourceService\(\)''',
r'''local function routeItemToScrapper(item)
    if not item or not item.Parent then return false end
    local beforeWood, beforeScrap = getCampTotals()
    local dropCF = getPhysicalScrapDrop()

    local function accepted()
        if not item.Parent then return true end
        local wood, scrap = getCampTotals()
        if beforeWood ~= nil and wood ~= nil and wood > beforeWood then return true end
        if beforeScrap ~= nil and scrap ~= nil and scrap > beforeScrap then return true end
        return false
    end

    for attempt = 1, 2 do
        if not item.Parent then return true end
        if not dragItemTo(item, dropCF) and item.Parent then
            task.wait(0.10)
        end

        local deadline = os.clock() + (attempt == 1 and 1.5 or 2.0)
        repeat
            task.wait(0.10)
            if accepted() then return true end
        until not state.active or os.clock() >= deadline
    end

    return accepted()
end

local function runResourceService()''',
'scrapper retry')

# Prefer coal/canisters/oil/etc. before logs while leveling, and a single stale
# item can no longer stop every other fuel/log from being processed.
replace_once(
'''        table.sort(candidates, function(a, b)
            if a.target ~= b.target then
                return a.target == "fire"
            end
            return a.distance < b.distance
        end)''',
'''        table.sort(candidates, function(a, b)
            if a.target ~= b.target then
                return a.target == "fire"
            end
            if a.target == "fire" then
                local aLog = isLogResource(a.item)
                local bLog = isLogResource(b.item)
                if aLog ~= bLog then
                    return not aLog
                end
            end
            return a.distance < b.distance
        end)''',
'fuel priority')

replace_once(
'''                if not handled then
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
                task.wait(0.05)''',
'''                if handled then
                    processed = processed + 1
                    if candidate.target == "fire" then
                        level = getCampfireLevel() or level
                        campfireMaxed = level >= state.campfireTargetLevel
                        fuelRatio = getCampfireFuelRatio()
                    end
                else
                    resourceCooldown[item] = os.clock() + 2.5
                end
                task.wait(0.05)''',
'resource stale-item isolation')

# Add reversible farm noclip so the travel tween cannot collide with terrain,
# trees or streamed structures. Persist originals globally so re-execution can
# restore collision state instead of inheriting an old noclip run.
replace_once(
'''G.SB99_PROMPT_ORIGINALS = setmetatable({}, { __mode = "k" })

local function track(connection)''',
'''G.SB99_PROMPT_ORIGINALS = setmetatable({}, { __mode = "k" })

if type(G.SB99_FARM_COLLISIONS) == "table" then
    for part, canCollide in pairs(G.SB99_FARM_COLLISIONS) do
        if typeof(part) == "Instance" and part.Parent and part:IsA("BasePart") then
            pcall(function()
                part.CanCollide = canCollide == true
            end)
        end
    end
end
G.SB99_FARM_COLLISIONS = setmetatable({}, { __mode = "k" })

local function track(connection)''',
'reexecution noclip restore')

replace_once(
'''local function lockFarmCharacter()
    local humanoid = getHumanoid()
    local root = getRoot()
''',
'''local function applyFarmNoclip()
    local character = getCharacter()
    if not character then return end
    local originals = G.SB99_FARM_COLLISIONS
    for _, part in ipairs(character:GetDescendants()) do
        if part:IsA("BasePart") then
            if originals[part] == nil then
                originals[part] = part.CanCollide
            end
            if part.CanCollide then
                pcall(function()
                    part.CanCollide = false
                end)
            end
        end
    end
end

local function restoreFarmNoclip()
    local originals = G.SB99_FARM_COLLISIONS
    if type(originals) ~= "table" then return end
    for part, canCollide in pairs(originals) do
        if typeof(part) == "Instance" and part.Parent and part:IsA("BasePart") then
            pcall(function()
                part.CanCollide = canCollide == true
            end)
        end
    end
    table.clear(originals)
end

local function lockFarmCharacter()
    local humanoid = getHumanoid()
    local root = getRoot()

    if state.autoFarm then
        applyFarmNoclip()
    end
''',
'farm noclip functions')

replace_once(
'''    destroyPlatform()
    restoreInstantPrompts()

    if character then''',
'''    destroyPlatform()
    restoreInstantPrompts()
    restoreFarmNoclip()

    if character then''',
'restore noclip on disable')

# A visited tree now gets a full 5-second service window. Travel remains Y=30,
# then a second noclip tween approaches the trunk instead of instant PivotTo.
replace_once('''        treeVisitCooldown[bestTree] = now + 4''', '''        treeVisitCooldown[bestTree] = now + 7''', 'tree revisit cooldown')

regex_once(
r'''                        if tree and tree.Parent and state.autoChop then\n.*?                        else\n                            task.wait\(0\.25\)\n                        end''',
r'''                        if tree and tree.Parent and state.autoChop then
                            local treePart = tree:FindFirstChild("Trunk", true)
                            if not (treePart and treePart:IsA("BasePart")) then
                                treePart = getPart(tree)
                            end

                            -- First leg is the normal Y=30 patrol tween. The
                            -- second leg approaches the trunk with noclip, so
                            -- terrain/tree collision cannot stop the farm short.
                            if treePart and treePart.Parent then
                                moveFarmTo(Vector3.new(
                                    treePart.Position.X,
                                    treePart.Position.Y + 5,
                                    treePart.Position.Z
                                ), false)
                            end

                            local holdUntil = os.clock() + 5
                            repeat
                                if tree and tree.Parent and smallTreeAvailable(tree) then
                                    attackTarget(tree, true)
                                end
                                -- Service newly spawned logs/fuel while we are
                                -- deliberately waiting at this tree.
                                runResourceService()
                                task.wait(0.14)
                            until not state.autoFarm
                                or state.strongholdControl
                                or isNight()
                                or os.clock() >= holdUntil

                            -- One final resource pass catches drops that replicated
                            -- at the end of the five-second chop window.
                            runResourceService()
                            task.wait(0.20)

                            if state.autoFarm and not state.strongholdControl and not isNight() then
                                local liveRoot = getRoot()
                                if liveRoot then
                                    moveFarmTo(Vector3.new(
                                        liveRoot.Position.X,
                                        FARM_PATROL_Y,
                                        liveRoot.Position.Z
                                    ), false)
                                end
                            end
                        else
                            task.wait(0.25)
                        end''',
'five second tree service')

TARGET.write_text(s, encoding='utf-8')
