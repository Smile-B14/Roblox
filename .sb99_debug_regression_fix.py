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

# Combat pressure: the debug report showed 40-70 concurrent RemoteFunction
# calls. Keep manual aura useful but prevent Auto Farm from saturating the
# combat remote while travelling above/below the map.
replace_once(
'''    range = 200,
    maxInflight = 72,
    inflight = 0,
    targetCooldown = 0.06,
    workerDelay = 0.008,''',
'''    range = 200,
    maxInflight = 16,
    inflight = 0,
    targetCooldown = 0.08,
    workerDelay = 0.012,''',
'combat pressure limits')

replace_once(
'''    campfireTargetLevel = 6,
    campfireMaintainThreshold = 0.80,
    resourcePassLimit = 64,
    resourcePickupRange = 320,''',
'''    campfireTargetLevel = 6,
    campfireMaintainThreshold = 0.80,
    fireDerivedLevel = math.clamp(tonumber(G.SB99_FIRE_DERIVED_LEVEL) or 1, 1, 6),
    fireLastTarget = tonumber(G.SB99_FIRE_LAST_TARGET),
    resourcePassLimit = 12,
    resourcePickupRange = 360,''',
'camp/resource state')

# Campfire level: live debug returned nil. Check both the Progress attribute and
# a ValueBase named Progress, then explicit fire/camp fields. As a final
# session-local fallback, FuelTarget changes advance the derived level.
regex_once(
r'''local function getCampfireLevel\(\).*?\nend\n\nlocal function getCampfireFuelRatio\(\)''',
r'''local function getCampfireLevel()
    local progress = tonumber(workspace:GetAttribute("Progress"))

    if progress == nil then
        local progressObject = workspace:FindFirstChild("Progress")
        if progressObject then
            local ok, value = pcall(function()
                return progressObject.Value
            end)
            if ok then
                progress = tonumber(value)
            end
        end
    end

    if progress ~= nil then
        local level = math.clamp(math.floor(progress + 0.001), 1, state.campfireTargetLevel)
        state.fireDerivedLevel = level
        G.SB99_FIRE_DERIVED_LEVEL = level
        return level
    end

    local fire = getMainFire()
    if not fire then
        return nil
    end

    local level = readNumberValue(fire, {
        "Progress", "CampfireProgress", "Level", "FireLevel", "CampfireLevel", "UpgradeLevel", "CurrentLevel",
    })
    if level == nil and fire.Parent then
        level = readNumberValue(fire.Parent, {
            "Progress", "CampfireProgress", "CampfireLevel", "FireLevel", "CurrentFireLevel", "MainFireLevel",
        })
    end
    if level == nil then
        level = readNumberValue(workspace, {
            "Progress", "CampfireProgress", "CampfireLevel", "FireLevel", "CurrentFireLevel", "MainFireLevel",
        })
    end

    if level ~= nil then
        level = math.clamp(math.floor(level + 0.001), 1, state.campfireTargetLevel)
        state.fireDerivedLevel = level
        G.SB99_FIRE_DERIVED_LEVEL = level
        return level
    end

    -- Some current servers expose FuelTarget immediately but do not replicate
    -- Progress to the client. FuelTarget changes only when the fire advances,
    -- so track those transitions for this server session rather than returning
    -- nil forever and burning every log indefinitely.
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
        return state.fireDerivedLevel
    end

    return nil
end

local function getCampfireFuelRatio()''',
'campfire level fallbacks')

# In unknown states, preserve resources instead of assuming "not max". Route
# fuel physically to the fire first; RequestBurnItem remains a near-fire
# fallback after server drag ownership/replication has occurred.
replace_once(
'''        local level = getCampfireLevel()
        local campfireMaxed = level ~= nil and level >= state.campfireTargetLevel
        local fuelRatio = getCampfireFuelRatio()''',
'''        local level = getCampfireLevel()
        if level == nil then
            return
        end
        local campfireMaxed = level >= state.campfireTargetLevel
        local fuelRatio = getCampfireFuelRatio()''',
'resource unknown-level fail safe')

replace_once(
'''                local handled = false
                if target == CAMPFIRE_DROP then
                    handled = burnItemIntoCampfire(item)
                    if not handled and item.Parent == items and candidate.distance <= state.resourcePickupRange then
                        handled = dragItemTo(item, CFrame.new(CAMPFIRE_DROP))
                    end
                else
                    handled = dragItemTo(item, CFrame.new(target))
                end''',
'''                local handled = false
                if target == CAMPFIRE_DROP then
                    -- The live game accepts fuel most reliably after normal drag
                    -- ownership and a physical drop at the fire. Do not remotely
                    -- burn objects from across the map.
                    handled = dragItemTo(item, CFrame.new(CAMPFIRE_DROP))
                    task.wait(0.10)

                    if item.Parent == items then
                        local part = getPart(item)
                        local nearFire = part and (part.Position - CAMPFIRE_DROP).Magnitude <= 24
                        if nearFire then
                            handled = burnItemIntoCampfire(item) or handled
                        end
                    else
                        handled = true
                    end
                else
                    handled = dragItemTo(item, CFrame.new(target))
                end''',
'physical fire routing')

# Keep the background aura local while Auto Farm is on the surface. At the
# under-map night position retain the full configured aura so planted trees and
# nearby enemies can still be serviced.
regex_once(
r'''local function sortedEntities\(root\)\n    local result = \{\}\n    local folder = workspace:FindFirstChild\("Characters"\).*?\n    return result\nend''',
r'''local function sortedEntities(root)
    local result = {}
    local folder = workspace:FindFirstChild("Characters")

    if not folder then
        return result
    end

    local maxRange = state.range
    if state.autoFarm and root.Position.Y >= 0 then
        maxRange = math.min(maxRange, 90)
    end

    for _, target in ipairs(folder:GetChildren()) do
        if target:IsA("Model") and target ~= player.Character and not isLostChild(target) and target.Name ~= "Pelt Trader" then
            local part = getPart(target)
            if part then
                local distance = (part.Position - root.Position).Magnitude
                if distance <= maxRange then
                    table.insert(result, {
                        target = target,
                        distance = distance,
                    })
                end
            end
        end
    end

    table.sort(result, function(a, b)
        return a.distance < b.distance
    end)

    return result
end''',
'focused farm entity aura')

regex_once(
r'''local function sortedTrees\(root\)\n    local result = \{\}.*?\n    return result\nend''',
r'''local function sortedTrees(root)
    local result = {}
    local maxRange = state.range
    if state.autoFarm and root.Position.Y >= 0 then
        maxRange = math.min(maxRange, 45)
    end

    for _, tree in ipairs(treeCache) do
        if tree.Parent then
            local part = getPart(tree)
            if part then
                local distance = (part.Position - root.Position).Magnitude
                if distance <= maxRange then
                    table.insert(result, {
                        target = tree,
                        distance = distance,
                    })
                end
            end
        end
    end

    table.sort(result, function(a, b)
        return a.distance < b.distance
    end)

    return result
end''',
'focused farm tree aura')

# Auto Farm must not begin with an immediate long food sweep under the map.
replace_once(
'''    -- Immediate first food sweep, then every minute.
    state.lastFoodService = 0

    createPlatform()
    setAllPromptsInstant()

    local character = getCharacter()
    if character then
        pcall(character.PivotTo, character, CFrame.new(FARM_HOME))
    end

    lockFarmCharacter()''',
'''    -- Start roaming immediately. Emergency hunger can still request food,
    -- while the normal collection/cooking sweep starts after one interval.
    state.lastFoodService = os.clock()

    createPlatform()
    setAllPromptsInstant()

    local character = getCharacter()
    local root = getRoot()
    if character then
        if isNight() then
            pcall(character.PivotTo, character, CFrame.new(FARM_HOME))
        elseif root then
            pcall(character.PivotTo, character, CFrame.new(root.Position.X, FARM_PATROL_Y, root.Position.Z))
        else
            pcall(character.PivotTo, character, CFrame.new(getFarmCenter()))
        end
    end

    lockFarmCharacter()''',
'farm startup position and food delay')

# Respawn also respects day/night instead of always forcing the under-map home.
replace_once(
'''        if state.strongholdControl then
            state.releaseFarmForStronghold()
        else
            pcall(character.PivotTo, character, CFrame.new(FARM_HOME))
            lockFarmCharacter()
        end''',
'''        if state.strongholdControl then
            state.releaseFarmForStronghold()
        else
            local root = character:FindFirstChild("HumanoidRootPart")
            if isNight() then
                pcall(character.PivotTo, character, CFrame.new(FARM_HOME))
            elseif root then
                pcall(character.PivotTo, character, CFrame.new(root.Position.X, FARM_PATROL_Y, root.Position.Z))
            else
                pcall(character.PivotTo, character, CFrame.new(getFarmCenter()))
            end
            lockFarmCharacter()
        end''',
'day-aware farm respawn')

# Daytime food service happens at the campfire surface rather than under map.
replace_once(
'''        -- Always stay under center while servicing food.
        local character = getCharacter()
        if character then
            pcall(character.PivotTo, character, CFrame.new(FARM_HOME))
        end
        lockFarmCharacter()''',
'''        local character = getCharacter()
        local servicePosition = isNight() and FARM_HOME or CHILD_CAMP_DROP
        if character then
            pcall(character.PivotTo, character, CFrame.new(servicePosition))
        end
        lockFarmCharacter()''',
'daytime food service position')

replace_once(
'''                elseif state.emergencyFoodRun or foodServiceDue() then
                    moveFarmTo(FARM_HOME, true)
                    runFoodService()
                    task.wait(0.2)''',
'''                elseif state.emergencyFoodRun or foodServiceDue() then
                    moveFarmTo(getFarmCenter(), true)
                    runFoodService()
                    task.wait(0.2)''',
'daytime food approach')

# Selected Small Trees are approached at Y=30, then serviced briefly at trunk
# height where the server accepts the same attacks that work with manual Auto
# Chop. Rise back to patrol height afterwards.
replace_once(
'''                        if tree and tree.Parent and state.autoChop then
                            -- Directly service the selected Small Tree while the
                            -- normal aura worker keeps handling nearby trees/enemies.
                            local chopDeadline = os.clock() + 1.1
                            repeat
                                attackTarget(tree, true)
                                task.wait(0.08)
                            until not state.autoFarm
                                or state.strongholdControl
                                or not smallTreeAvailable(tree)
                                or os.clock() >= chopDeadline
                        else
                            task.wait(0.25)
                        end''',
'''                        if tree and tree.Parent and state.autoChop then
                            -- Travel stays at Y=30, but actual chopping is done at
                            -- the tree's replicated trunk height. The debug probe
                            -- showed manual chopping working around ground level
                            -- while Auto Farm was attacking from ~27 studs above.
                            local treePart = tree:FindFirstChild("Trunk", true)
                            if not (treePart and treePart:IsA("BasePart")) then
                                treePart = getPart(tree)
                            end

                            local character = getCharacter()
                            if treePart and character then
                                pcall(character.PivotTo, character, CFrame.new(
                                    treePart.Position.X,
                                    treePart.Position.Y + 4,
                                    treePart.Position.Z
                                ))
                                lockFarmCharacter()
                                task.wait(0.10)
                            end

                            local chopDeadline = os.clock() + 3
                            repeat
                                attackTarget(tree, true)
                                task.wait(0.09)
                            until not state.autoFarm
                                or state.strongholdControl
                                or not smallTreeAvailable(tree)
                                or os.clock() >= chopDeadline

                            if state.autoFarm and not state.strongholdControl and not isNight() then
                                local liveRoot = getRoot()
                                if liveRoot and character and character.Parent then
                                    pcall(character.PivotTo, character, CFrame.new(
                                        liveRoot.Position.X,
                                        FARM_PATROL_Y,
                                        liveRoot.Position.Z
                                    ))
                                    lockFarmCharacter()
                                end
                            end
                        else
                            task.wait(0.25)
                        end''',
'ground-level focused chop')

# Shorter hung-combat release now that concurrency is intentionally bounded.
replace_once('''    task.delay(2, function()
        if released then''', '''    task.delay(1, function()
        if released then''', 'combat timeout')

# Keep the compact status useful for the next live verification.
replace_once(
'''            "Fire %s/6 | Axe %s | Trees %d\\nSmart %s | SH %s | Diamonds %s",''',
'''            "Fire %s/6 | Axe %s | Trees %d | Inflight %d\\nSmart %s | SH %s | Diamonds %s",''',
'ui status format')
replace_once(
'''            #treeCache,
            state.smartResources and "ON" or "OFF",''',
'''            #treeCache,
            state.inflight,
            state.smartResources and "ON" or "OFF",''',
'ui status inflight value')

TARGET.write_text(s, encoding='utf-8')
