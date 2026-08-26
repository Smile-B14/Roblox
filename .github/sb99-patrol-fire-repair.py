from pathlib import Path
import re

TARGET = Path('99 Nights Helper Godmode')
s = TARGET.read_text(encoding='utf-8')


def replace_once(old, new, label):
    global s
    count = s.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 exact match, got {count}')
    s = s.replace(old, new, 1)


def sub_once(pattern, repl, label, flags=0):
    global s
    s2, count = re.subn(pattern, repl, s, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 regex match, got {count}')
    s = s2

replace_once(
'''    patrolSpeed = 38,\n    strongAxePatrolSpeed = 52,\n    patrolIndex = 1,\n    patrolExploreIndex = 0,\n''',
'''    patrolSpeed = 46,\n    strongAxePatrolSpeed = 64,\n    patrolIndex = 0,\n    patrolExploreIndex = 0,\n    treeServiceEvery = 4,\n    treeHoldSeconds = 1.6,\n    treeApproachSpeed = 90,\n''',
'patrol state')

replace_once(
'''    fireDerivedLevel = math.clamp(tonumber(G.SB99_FIRE_DERIVED_LEVEL) or 1, 1, 6),\n    fireLastTarget = tonumber(G.SB99_FIRE_LAST_TARGET),\n    resourcePassLimit = 24,\n    resourcePickupRange = 2000,\n''',
'''    -- Never inherit an inferred fire level from an older execution/server.\n    -- workspace.Progress is authoritative when available; FuelTarget transitions\n    -- are only a fallback for the current execution.\n    fireDerivedLevel = 1,\n    fireLastTarget = nil,\n    resourcePassLimit = 48,\n    resourcePickupRange = 10000,\n''',
'fire state')

replace_once(
'''G.SB99_STATE = state\nG.SB99_CAMP_BUILD_DONE = state.campBuildDone\nG.SB99_SAPLING_SLOT = state.saplingSlot\n''',
'''G.SB99_STATE = state\nG.SB99_CAMP_BUILD_DONE = state.campBuildDone\nG.SB99_SAPLING_SLOT = state.saplingSlot\n-- Clear stale cross-execution fire inference. This data is session-local only.\nG.SB99_FIRE_DERIVED_LEVEL = nil\nG.SB99_FIRE_LAST_TARGET = nil\n''',
'clear stale fire inference')

replace_once(
'''local function isFuelResource(item)\n    if not item then\n        return false\n    end\n    local name = lowerName(item)\n    if FUEL_NAMES[name] or isLogResource(item) then\n        return true\n    end\n\n    local fuel = tonumber(item:GetAttribute("FuelAmount"))\n        or tonumber(item:GetAttribute("FuelValue"))\n        or tonumber(item:GetAttribute("BurnValue"))\n        or tonumber(item:GetAttribute("Fuel"))\n    return fuel ~= nil and fuel > 0\nend\n''',
'''local function isFuelResource(item)\n    if not item then\n        return false\n    end\n    local name = lowerName(item)\n    if FUEL_NAMES[name] or isLogResource(item) then\n        return true\n    end\n\n    local fuel = tonumber(item:GetAttribute("FuelAmount"))\n        or tonumber(item:GetAttribute("FuelValue"))\n        or tonumber(item:GetAttribute("BurnValue"))\n        or tonumber(item:GetAttribute("Fuel"))\n    return fuel ~= nil and fuel > 0\nend\n\nlocal function fuelPriority(item)\n    local name = lowerName(item)\n    if name == "coal" or name == "charcoal" then return 120 end\n    if name == "fuel canister" or name == "gas canister" then return 115 end\n    if name == "oil barrel" or name == "gasoline" or name == "kerosene" then return 110 end\n    if name == "biofuel" or name == "propane tank" then return 105 end\n    if name == "chair" then return 80 end\n    if isLogResource(item) then return 20 end\n    return 60\nend\n''',
'fuel priority')

sub_once(
    r'local function burnItemIntoCampfire\(item\)\n.*?\nend\n\nlocal function routeItemToScrapper',
'''local function burnItemIntoCampfire(item)\n    if not item or not item.Parent then return false end\n    local fire = getMainFire()\n    if not fire then return false end\n\n    local beforeFuel = tonumber(fire:GetAttribute("FuelRemaining")) or 0\n    local beforeTarget = tonumber(fire:GetAttribute("FuelTarget"))\n    local beforeLevel = getCampfireLevel() or tonumber(state.fireDerivedLevel) or 1\n\n    local function accepted()\n        if not item.Parent then\n            return true\n        end\n        local liveFire = getMainFire()\n        if not liveFire then return false end\n        local afterFuel = tonumber(liveFire:GetAttribute("FuelRemaining")) or 0\n        local afterTarget = tonumber(liveFire:GetAttribute("FuelTarget"))\n        local afterLevel = getCampfireLevel() or beforeLevel\n        return afterFuel > beforeFuel + 0.001\n            or afterLevel > beforeLevel\n            or (beforeTarget ~= nil and afterTarget ~= nil and math.abs(afterTarget - beforeTarget) > 0.001)\n    end\n\n    local function requestBurn()\n        if not isLive(RequestBurnItem) then refreshRemotes() end\n        local remote = RequestBurnItem\n        if not isLive(remote) then return false end\n\n        -- Current game flow accepts MainFire + fuel item directly. Do not put\n        -- RemoteEvents behind the generic RemoteFunction timeout/cooldown layer.\n        if remote:IsA("RemoteEvent") then\n            return pcall(remote.FireServer, remote, fire, item)\n        elseif remote:IsA("RemoteFunction") then\n            local ok, response = callUtilityRemote(remote, 1.25, fire, item)\n            return ok and response ~= false\n        end\n        return false\n    end\n\n    -- Fast path: direct burn first. Two short sends are cheaper and more\n    -- reliable than blocking the whole resource service for ~2 seconds/item.\n    for _ = 1, 2 do\n        if not item.Parent then return true end\n        requestBurn()\n        task.wait(0.08)\n        if accepted() then return true end\n    end\n\n    if not item.Parent then return true end\n\n    -- Fallback for servers that require drag ownership/proximity.\n    local dropCF = getPhysicalFireDrop()\n    local moved = dragItemTo(item, dropCF)\n    if item.Parent then\n        requestBurn()\n    end\n    task.wait(0.12)\n\n    return accepted() or (moved and not item.Parent)\nend\n\nlocal function routeItemToScrapper''',
    'burn function',
    flags=re.S)

replace_once(
'''                local target = resourceTarget(item, campfireMaxed, fuelRatio)\n                if target then\n                    local part = getPart(item)\n                    if part then\n                        local distance = (part.Position - root.Position).Magnitude\n                        if distance <= state.resourcePickupRange then\n                            table.insert(candidates, {\n                                item = item,\n                                target = target,\n                                distance = distance,\n                            })\n                        end\n                    end\n                end\n''',
'''                local target = resourceTarget(item, campfireMaxed, fuelRatio)\n                if target then\n                    local part = getPart(item)\n                    local distance = part and (part.Position - root.Position).Magnitude or math.huge\n                    -- Fire fuel uses RequestBurnItem and does not need to be near\n                    -- the player. Scrap still requires a physical draggable part.\n                    if target == "fire" or (part and distance <= state.resourcePickupRange) then\n                        table.insert(candidates, {\n                            item = item,\n                            target = target,\n                            distance = distance,\n                        })\n                    end\n                end\n''',
'resource candidate range')

replace_once(
'''            if a.target == "fire" then\n                local aLog = isLogResource(a.item)\n                local bLog = isLogResource(b.item)\n                if aLog ~= bLog then\n                    return not aLog\n                end\n            end\n            return a.distance < b.distance\n''',
'''            if a.target == "fire" then\n                local ap = fuelPriority(a.item)\n                local bp = fuelPriority(b.item)\n                if ap ~= bp then\n                    return ap > bp\n                end\n            end\n            return a.distance < b.distance\n''',
'resource fuel sort')

replace_once(
'''            local item = candidate.item\n            if item and item.Parent == items then\n                resourceCooldown[item] = os.clock() + 1\n                local handled = candidate.target == "fire"\n                    and burnItemIntoCampfire(item)\n                    or routeItemToScrapper(item)\n''',
'''            local item = candidate.item\n            if item and item.Parent == items then\n                -- Re-evaluate after every successful fuel item. Reaching Level 6\n                -- can change a queued Log from fire fuel into scrapper material.\n                local liveTarget = resourceTarget(item, campfireMaxed, fuelRatio)\n                if liveTarget ~= candidate.target then\n                    continue\n                end\n\n                resourceCooldown[item] = os.clock() + 0.6\n                local handled = candidate.target == "fire"\n                    and burnItemIntoCampfire(item)\n                    or routeItemToScrapper(item)\n''',
'resource live target')

replace_once(
'''local function moveFarmTo(position, ignoreInterrupts)\n''',
'''local function moveFarmTo(position, ignoreInterrupts, speedOverride)\n''',
'move signature')

replace_once(
'''    local patrolSpeed = state.patrolSpeed\n''',
'''    local patrolSpeed = tonumber(speedOverride) or state.patrolSpeed\n''',
'move speed override')

replace_once(
'''        treeVisitCooldown[bestTree] = now + 7\n''',
'''        treeVisitCooldown[bestTree] = now + 12\n''',
'tree revisit cooldown')

replace_once(
'''local function nextDayFarmTarget()\n    local treePoint, tree = chooseSmallTreeTarget()\n    if treePoint then\n        return treePoint, tree\n    end\n    return nextExploreTarget(), nil\nend\n''',
'''local function nextDayFarmTarget()\n    -- Exploration owns the route. Trees are opportunistic stops instead of\n    -- permanently starving chest/map/enemy patrol when foliage is dense.\n    state.patrolIndex = (tonumber(state.patrolIndex) or 0) + 1\n    if state.patrolIndex % math.max(2, tonumber(state.treeServiceEvery) or 4) == 0 then\n        local treePoint, tree = chooseSmallTreeTarget()\n        if treePoint then\n            return treePoint, tree\n        end\n    end\n    return nextExploreTarget(), nil\nend\n''',
'patrol alternation')

replace_once(
'''    state.patrolIndex = 1\n    state.patrolExploreIndex = 0\n''',
'''    state.patrolIndex = 0\n    state.patrolExploreIndex = 0\n    state.resourcePauseUntil = 0\n''',
'enable farm counters')

old_tree = '''                        if tree and tree.Parent and state.autoChop then\n                            local treePart = tree:FindFirstChild("Trunk", true)\n                            if not (treePart and treePart:IsA("BasePart")) then\n                                treePart = getPart(tree)\n                            end\n\n                            -- First leg is the normal Y=30 patrol tween. The\n                            -- second leg approaches the trunk with noclip, so\n                            -- terrain/tree collision cannot stop the farm short.\n                            if treePart and treePart.Parent then\n                                moveFarmTo(Vector3.new(\n                                    treePart.Position.X,\n                                    treePart.Position.Y + 5,\n                                    treePart.Position.Z\n                                ), false)\n                            end\n\n                            local holdUntil = os.clock() + 5\n                            repeat\n                                if tree and tree.Parent and smallTreeAvailable(tree) then\n                                    attackTarget(tree, true)\n                                end\n                                -- Service newly spawned logs/fuel while we are\n                                -- deliberately waiting at this tree.\n                                runResourceService()\n                                task.wait(0.14)\n                            until not state.autoFarm\n                                or state.strongholdControl\n                                or isNight()\n                                or os.clock() >= holdUntil\n\n                            -- One final resource pass catches drops that replicated\n                            -- at the end of the five-second chop window.\n                            runResourceService()\n                            task.wait(0.20)\n\n                            if state.autoFarm and not state.strongholdControl and not isNight() then\n                                local liveRoot = getRoot()\n                                if liveRoot then\n                                    moveFarmTo(Vector3.new(\n                                        liveRoot.Position.X,\n                                        FARM_PATROL_Y,\n                                        liveRoot.Position.Z\n                                    ), false)\n                                end\n                            end\n                        else\n                            task.wait(0.25)\n                        end\n'''
new_tree = '''                        if tree and tree.Parent and state.autoChop then\n                            local treePart = tree:FindFirstChild("Trunk", true)\n                            if not (treePart and treePart:IsA("BasePart")) then\n                                treePart = getPart(tree)\n                            end\n\n                            -- Travel stays at Y=30. Only the short vertical tree\n                            -- approach uses the faster noclip tween.\n                            if treePart and treePart.Parent then\n                                moveFarmTo(Vector3.new(\n                                    treePart.Position.X,\n                                    treePart.Position.Y + 5,\n                                    treePart.Position.Z\n                                ), false, state.treeApproachSpeed)\n                            end\n\n                            local holdUntil = os.clock() + (tonumber(state.treeHoldSeconds) or 1.6)\n                            repeat\n                                if tree and tree.Parent and smallTreeAvailable(tree) then\n                                    attackTarget(tree, true)\n                                end\n                                task.wait(0.12)\n                            until not state.autoFarm\n                                or state.strongholdControl\n                                or isNight()\n                                or not smallTreeAvailable(tree)\n                                or os.clock() >= holdUntil\n\n                            -- Resource routing already owns its own background loop;\n                            -- never block patrol waiting on coal/log verification.\n                            if state.autoFarm and not state.strongholdControl and not isNight() then\n                                local liveRoot = getRoot()\n                                if liveRoot then\n                                    moveFarmTo(Vector3.new(\n                                        liveRoot.Position.X,\n                                        FARM_PATROL_Y,\n                                        liveRoot.Position.Z\n                                    ), false, state.treeApproachSpeed)\n                                end\n                            end\n                        else\n                            task.wait(0.12)\n                        end\n'''
replace_once(old_tree, new_tree, 'tree service controller')

replace_once(
'''    if v then table.clear(resourceCooldown); state.resourceServiceRunning = false end\n''',
'''    if v then\n        table.clear(resourceCooldown)\n        state.resourceServiceRunning = false\n        state.resourcePauseUntil = 0\n    end\n''',
'smart resource restart')

# Required behavior assertions.
required = [
    'treeServiceEvery = 4',
    'treeHoldSeconds = 1.6',
    'state.patrolIndex % math.max(2',
    'fuelPriority(item)',
    'if target == "fire" or (part and distance <= state.resourcePickupRange)',
    'fireDerivedLevel = 1',
    'G.SB99_FIRE_DERIVED_LEVEL = nil',
    'moveFarmTo(position, ignoreInterrupts, speedOverride)',
]
for needle in required:
    if needle not in s:
        raise SystemExit(f'missing required marker: {needle}')

if 'local holdUntil = os.clock() + 5' in s:
    raise SystemExit('old 5-second blocking tree hold still present')
if 'fireDerivedLevel = math.clamp(tonumber(G.SB99_FIRE_DERIVED_LEVEL)' in s:
    raise SystemExit('stale fire-level persistence still present')

TARGET.write_text(s, encoding='utf-8')
print('patched', TARGET, 'bytes=', len(s.encode('utf-8')))
