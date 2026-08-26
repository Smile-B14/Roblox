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

# Exact remote discovered from uploaded place: RequestScrapItem is a RemoteFunction.
once(
    'local RequestBurnItem = nil\n',
    'local RequestBurnItem = nil\nlocal RequestScrapItem = nil\n',
    'declare RequestScrapItem',
)
once(
    '    RequestBurnItem = findReplicated("RequestBurnItem")\n',
    '    RequestBurnItem = findReplicated("RequestBurnItem")\n    RequestScrapItem = findReplicated("RequestScrapItem")\n',
    'refresh RequestScrapItem',
)
once(
    '        or name == "RequestBurnItem" then\n',
    '        or name == "RequestBurnItem"\n        or name == "RequestScrapItem" then\n',
    'refresh on RequestScrapItem replication',
)

# The uploaded place shows the game requires BurnFuel, while Logs can also be
# tagged CanBeGrinded for the grinder. Prefer those authoritative signals.
once(
'''    local name = lowerName(item)\n    if FUEL_NAMES[name] or isLogResource(item) then\n        return true\n    end\n    -- Entity corpses are also legitimate campfire fuel in current builds.\n''',
'''    local name = lowerName(item)\n    local burnFuel = tonumber(item:GetAttribute("BurnFuel"))\n    if (burnFuel ~= nil and burnFuel > 0) or FUEL_NAMES[name] or isLogResource(item) then\n        return true\n    end\n    -- Entity corpses are also legitimate campfire fuel in current builds.\n''',
    'BurnFuel detection',
)
once(
'''    -- Current game marks generic craft/scrap objects directly.\n    if item:GetAttribute("Scrappable") == true then\n        return true\n    end\n\n    local name = lowerName(item)\n''',
'''    -- Current game marks generic craft/scrap objects directly. Scrappable is\n    -- numeric in the live place, and Logs can use the CanBeGrinded tag.\n    local scrappable = tonumber(item:GetAttribute("Scrappable"))\n    if (scrappable ~= nil and scrappable > 0)\n        or item:HasTag("CanBeGrinded")\n        or item:HasTag("Gem")\n        or item:HasTag("GreenGem") then\n        return true\n    end\n\n    local name = lowerName(item)\n''',
    'Scrappable/tag detection',
)

# Exact combat flow from the uploaded place:
# EnemyHandler.ApplyLocalDamage(target, damage) -> generated per-user hit id,
# then ToolDamageObject(target, RealModel, hitId, HRP.CFrame, optionalFinalHit).
# Also equip through InventoryHandler.RequestEquipItem rather than trying to
# fire the server->client EquipItemHandle event from the executor.
combat = r'''local lastArmed = nil
local lastArmTime = 0

local function getGameClient()
    if type(state.gameClient) == "table" then
        return state.gameClient
    end
    local scripts = player:FindFirstChild("PlayerScripts")
    local module = scripts and scripts:FindFirstChild("Client")
    if module and module:IsA("ModuleScript") then
        local ok, client = pcall(require, module)
        if ok and type(client) == "table" then
            state.gameClient = client
            return client
        end
    end
    return nil
end

local function getEnemyHandler()
    local client = getGameClient()
    local handler = client and client.EnemyHandler
    return type(handler) == "table" and handler or nil
end

local function ensureAxeArmed(weapon)
    if not weapon or not weapon.Parent then
        return false
    end

    local now = os.clock()
    if weapon == lastArmed and now - lastArmTime < 0.75 then
        return true
    end

    local client = getGameClient()
    local inventoryHandler = client and client.InventoryHandler
    if type(inventoryHandler) == "table" then
        local current = nil
        if type(inventoryHandler.GetCurrentlyEquipped) == "function" then
            local ok, value = pcall(inventoryHandler.GetCurrentlyEquipped)
            if ok then current = value end
        end
        if current ~= weapon and type(inventoryHandler.RequestEquipItem) == "function" then
            pcall(inventoryHandler.RequestEquipItem, weapon)
            task.wait(0.03)
        end
    end

    lastArmed = weapon
    lastArmTime = now
    return true
end

local function makeLocalHit(target, damage)
    local handler = getEnemyHandler()
    if handler and type(handler.ApplyLocalDamage) == "function" then
        local ok, hitId, undo = pcall(handler.ApplyLocalDamage, target, damage)
        if ok and hitId ~= nil then
            return hitId, undo, handler
        end
    end

    -- Fallback exactly matches EnemyHandler.ApplyLocalDamage's live format.
    state.hitSequence = (tonumber(state.hitSequence) or 0) + 1
    return tostring(state.hitSequence) .. "_" .. tostring(math.abs(player.UserId)), nil, handler
end

local attackCooldown = setmetatable({}, { __mode = "k" })

local function attackTarget(target, isTree)
    if not isLive(ToolDamageObject) then
        refreshRemotes()
        if not isLive(ToolDamageObject) then return false end
    end
    if not target or not target.Parent then return false end

    local typeInflight = isTree and state.treeInflight or state.entityInflight
    local typeLimit = isTree and state.maxTreeInflight or state.maxEntityInflight
    if state.inflight >= state.maxInflight or typeInflight >= typeLimit then
        return false
    end

    if not isTree then
        local humanoid = target:FindFirstChildOfClass("Humanoid") or target:FindFirstChild("NPC")
        if humanoid then
            local health = tonumber(humanoid.Health) or tonumber(humanoid:GetAttribute("Health"))
            if health ~= nil and health <= 0 then return false end
            if humanoid:GetAttribute("Dead") == true then return false end
        end
    end

    local root = getRoot()
    local weapon = bestAxe
    if not weapon or not weapon.Parent then
        weapon = select(1, findBestOwned(axeScore))
        bestAxe = weapon
    end
    if not root or not root.Parent or not weapon or not weapon.Parent then return false end

    local now = os.clock()
    local previous = attackCooldown[target]
    if previous and now - previous < state.targetCooldown then return false end
    attackCooldown[target] = now

    ensureAxeArmed(weapon)
    local damage = tonumber(weapon:GetAttribute(isTree and "WeaponResourceDamage" or "WeaponDamage")) or 10
    local hitId, undoLocalDamage, enemyHandler = makeLocalHit(target, damage)
    if hitId == nil then return false end

    local finalStrike = false
    if isTree and enemyHandler and type(enemyHandler.GetLocalHealthRegistered) == "function" then
        local registers = target:FindFirstChild("HitRegisters")
        local health = tonumber(target:GetAttribute("Health"))
        if registers and health ~= nil then
            local ok, registered = pcall(enemyHandler.GetLocalHealthRegistered, registers)
            registered = ok and tonumber(registered) or nil
            if registered ~= nil then
                finalStrike = health - registered <= 0
            end
        end
    end

    local remote = ToolDamageObject
    local released = false
    local function reserveInflight()
        state.inflight += 1
        if isTree then state.treeInflight += 1 else state.entityInflight += 1 end
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
    local function rejected()
        state.lastAttackRejected = os.clock()
        if type(undoLocalDamage) == "function" then pcall(undoLocalDamage) end
    end

    if remote:IsA("RemoteEvent") then
        reserveInflight()
        local ok = pcall(remote.FireServer, remote, target, weapon, hitId, root.CFrame, finalStrike)
        if ok then state.lastAttackAccepted = os.clock() else rejected() end
        releaseInflight()
        return ok
    end
    if not remote:IsA("RemoteFunction") then
        if type(undoLocalDamage) == "function" then pcall(undoLocalDamage) end
        return false
    end

    reserveInflight()
    local attackThread = task.spawn(function()
        local ok, response = pcall(remote.InvokeServer, remote, target, weapon, hitId, root.CFrame, finalStrike)
        local accepted = ok and (response == true or (type(response) == "table" and response.Success == true))
        if accepted then
            state.lastAttackAccepted = os.clock()
        else
            rejected()
        end
        releaseInflight()
    end)

    task.delay(1.5, function()
        if released then return end
        if type(task.cancel) == "function" then pcall(task.cancel, attackThread) end
        rejected()
        releaseInflight()
    end)
    return true
end

local treeCache = {}'''
regex_once(r'local lastArmed = nil\n.*?\nlocal treeCache = \{\}', combat, 'exact place combat block')

# Auto Farm previously anchored HumanoidRootPart all day. Manual Auto Chop did
# not, and the live tool sends the current HRP CFrame to the server. Keep the
# under-map night lock anchored, but surface/child/stronghold movement unanchored.
once(
'''            if not root.Anchored then\n                root.Anchored = true\n            end\n''',
'''            local shouldAnchor = root.Position.Y < -20 and not state.strongholdControl\n            if root.Anchored ~= shouldAnchor then\n                root.Anchored = shouldAnchor\n            end\n''',
    'surface unanchor',
)

# Do not call a kid rescued merely because it is geographically near camp. The
# uploaded place's kid systems use the Rescued attribute as the authoritative
# state.
regex_once(
    r'local function childIsAtCamp\(child\)\n.*?\nend\n\nlocal function getUnrescuedChildren\(\)',
'''local function childIsAtCamp(child)
    if not child or not child.Parent then return false end
    local rescued = child:GetAttribute("Rescued")
    if rescued == true or rescued == 1 or rescued == "true" then return true end
    for _, name in ipairs({ "Saved", "AtCamp", "IsRescued" }) do
        local value = child:GetAttribute(name)
        if value == true or value == 1 or value == "true" then return true end
    end
    return false
end

local function getUnrescuedChildren()''',
    'authoritative child rescue state',
)

# Replace the bag transport with the exact live API. ItemBag is the actual
# storage folder; ItemBag tools are identified by tag and NumberItems may be nil
# until the client updates its UI. RequestBagDropItem requires a third last-item
# boolean, which the old helper omitted.
child_block = r'''local function getSackStoredCount(sack)
    if not sack then return 0 end
    local count = tonumber(sack:GetAttribute("NumberItems"))
    if count ~= nil then return math.max(0, count) end
    local itemBag = getItemBag()
    return itemBag and #itemBag:GetChildren() or 0
end

local function isStorageBag(item)
    if not item or not item.Parent then return false end
    local tagged = false
    pcall(function() tagged = item:HasTag("ItemBag") end)
    return tagged or isSack(item) or (tonumber(item:GetAttribute("Capacity")) or 0) > 0
end

local function getBagCapacity(item)
    if not item then return 0 end
    local client = getGameClient()
    local utility = client and client.Utility
    if utility and type(utility.GetItemBagSpace) == "function" then
        local ok, value = pcall(utility.GetItemBagSpace, item, player)
        value = ok and tonumber(value) or nil
        if value then return math.max(0, value) end
    end
    return math.max(0, tonumber(item:GetAttribute("Capacity")) or 0)
end

local function getRescueBags(requiredSlots)
    local bags, seen = {}, {}
    local inventory = player:FindFirstChild("Inventory")
    local containers = {}
    if inventory then table.insert(containers, inventory) end
    for _, container in ipairs(ownedContainers()) do
        if container and container ~= inventory then table.insert(containers, container) end
    end

    for _, container in ipairs(containers) do
        for _, item in ipairs(container:GetChildren()) do
            if not seen[item] and isStorageBag(item) then
                seen[item] = true
                local capacity = getBagCapacity(item)
                local count = getSackStoredCount(item)
                table.insert(bags, {
                    item = item,
                    free = math.max(0, capacity - count),
                    preferred = item.Name == "Old Sack" and 2 or (isSack(item) and 1 or 0),
                })
            end
        end
    end

    table.sort(bags, function(a, b)
        local af, bf = a.free >= requiredSlots, b.free >= requiredSlots
        if af ~= bf then return af end
        if a.preferred ~= b.preferred then return a.preferred > b.preferred end
        return a.free > b.free
    end)
    return bags
end

local function chooseRescueSack(requiredSlots)
    local info = getRescueBags(requiredSlots)[1]
    if not info or info.free < requiredSlots then return nil, 0 end
    return info.item, info.free
end

local function equipOwnedItem(item)
    if not item or not item.Parent then return false end
    local client = getGameClient()
    local handler = client and client.InventoryHandler
    if handler and type(handler.RequestEquipItem) == "function" then
        local ok = pcall(handler.RequestEquipItem, item)
        if ok then return true end
    end
    return false
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
    if not missing then return result end
    for key, position in pairs(missing:GetAttributes()) do
        if typeof(position) == "Vector3" then
            table.insert(result, { key = tostring(key), position = position })
        end
    end
    table.sort(result, function(a, b) return a.key < b.key end)
    return result
end

local function reacquireChild(childName)
    local characters = workspace:FindFirstChild("Characters")
    local exact = characters and characters:FindFirstChild(childName)
    return exact and exact:IsA("Model") and exact or nil
end

local function childStoredInItemBag(childName)
    local itemBag = getItemBag()
    if not itemBag then return false end
    for _, object in ipairs(itemBag:GetChildren()) do
        if object.Name == childName and isLostChild(object) then return true end
    end
    return false
end

local function storeChildInSack(sack, child)
    if not state.autoFarm or not state.autoChildRescue or state.strongholdControl
        or not sack or not sack.Parent or not child or not child.Parent then
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

    child = reacquireChild(childName) or child
    if not child or not child.Parent then return childStoredInItemBag(childName) end
    if child:GetAttribute("Rescued") == true then
        state.childRescueVerified[childName] = true
        return true
    end

    if not isLive(RequestBagStoreItem) then refreshRemotes() end
    if not isLive(RequestBagStoreItem) then return false end

    local before = getSackStoredCount(sack)
    local ok, response = callUtilityRemote(RequestBagStoreItem, 2, sack, child)
    local accepted = ok and (response == true or (type(response) == "table" and response.Success == true))
    if not accepted then return false end

    local deadline = os.clock() + 1.5
    repeat
        if childStoredInItemBag(childName) or getSackStoredCount(sack) > before then
            state.childRescueObserved[childName] = true
            return true
        end
        local live = reacquireChild(childName)
        if live and live:GetAttribute("Rescued") == true then
            state.childRescueVerified[childName] = true
            return true
        end
        task.wait(0.08)
    until not state.active or os.clock() >= deadline

    return childStoredInItemBag(childName)
end

local function getBaggedChildren()
    local result = {}
    local itemBag = getItemBag()
    if not itemBag then return result end
    for _, object in ipairs(itemBag:GetChildren()) do
        if isLostChild(object) then table.insert(result, object) end
    end
    return result
end

local function dropChildrenAtCamp(usedBags)
    local character = getCharacter()
    if character then pcall(character.PivotTo, character, CFrame.new(CHILD_CAMP_DROP)) end
    lockFarmCharacter()
    focusCameraAt(CHILD_CAMP_DROP)
    task.wait(1)

    if not isLive(RequestBagDropItem) then refreshRemotes() end
    if not isLive(RequestBagDropItem) then return false end

    local bags = {}
    for bag in pairs(usedBags) do
        if bag and bag.Parent then table.insert(bags, bag) end
    end
    for _, info in ipairs(getRescueBags(0)) do
        if info.item and info.item.Parent and not usedBags[info.item] then
            table.insert(bags, info.item)
        end
    end
    if #bags == 0 then return false end

    local droppedAny = false
    for _, child in ipairs(getBaggedChildren()) do
        if not state.autoFarm or state.strongholdControl then break end
        local childName = child.Name
        local bag = bags[1]
        local remaining = #getBaggedChildren()

        local sent = false
        if RequestBagDropItem:IsA("RemoteEvent") then
            sent = pcall(RequestBagDropItem.FireServer, RequestBagDropItem, bag, child, remaining <= 1)
        elseif RequestBagDropItem:IsA("RemoteFunction") then
            local ok, response = callUtilityRemote(RequestBagDropItem, 1.5, bag, child, remaining <= 1)
            sent = ok and response ~= false
        end

        if sent then
            local deadline = os.clock() + 2.5
            repeat
                local live = reacquireChild(childName)
                if live and childIsAtCamp(live) then
                    state.childRescueVerified[childName] = true
                    droppedAny = true
                    break
                end
                if not childStoredInItemBag(childName) then
                    droppedAny = true
                end
                task.wait(0.1)
            until not state.active or os.clock() >= deadline
        end
        task.wait(0.15)
    end

    task.wait(0.75)
    getUnrescuedChildren()
    return droppedAny
end

local function runChildRescueAttempt()'''
regex_once(
    r'local function getSackStoredCount\(sack\)\n.*?\nlocal function runChildRescueAttempt\(\)',
    child_block,
    'exact child bag flow',
)

# Direct server-backed resource actions from the uploaded place. Never touch the
# fire/grinder zones before server confirmation: those client scripts remove the
# object optimistically and were the reason items appeared to vanish.
resource_block = r'''local function getCraftingBenchReceiver()
    local campground = workspace:FindFirstChild("Map")
    campground = campground and campground:FindFirstChild("Campground")
    local direct = campground and campground:FindFirstChild("CraftingBench")
    if direct then return direct end
    local service = game:GetService("CollectionService")
    for _, bench in ipairs(service:GetTagged("CraftingBench")) do
        if bench:IsDescendantOf(workspace) then return bench end
    end
    return nil
end

local function fireStateChanged(item, fire, beforeFuel, beforeTarget, beforeLevel)
    if not item.Parent then return true end
    if not fire or not fire.Parent then return false end
    local fuel = tonumber(fire:GetAttribute("FuelRemaining"))
    local target = tonumber(fire:GetAttribute("FuelTarget"))
    local level = getCampfireLevel()
    return (fuel ~= nil and beforeFuel ~= nil and fuel > beforeFuel + 0.001)
        or (target ~= nil and beforeTarget ~= nil and math.abs(target - beforeTarget) > 0.001)
        or (level ~= nil and beforeLevel ~= nil and level > beforeLevel)
end

local function burnItemIntoCampfire(item)
    if not item or not item.Parent then return false end
    local fire = getMainFire()
    if not fire then return false end
    if (tonumber(item:GetAttribute("Wet")) or 0) >= 1 then return false end

    local owner = item:GetAttribute("Owner")
    if owner ~= nil and tonumber(owner) ~= player.UserId and tostring(owner) ~= tostring(player.UserId) then
        return false
    end

    if not isLive(RequestBurnItem) then refreshRemotes() end
    if not isLive(RequestBurnItem) then return false end

    local beforeFuel = tonumber(fire:GetAttribute("FuelRemaining"))
    local beforeTarget = tonumber(fire:GetAttribute("FuelTarget"))
    local beforeLevel = getCampfireLevel()

    local function send()
        if RequestBurnItem:IsA("RemoteEvent") then
            return pcall(RequestBurnItem.FireServer, RequestBurnItem, fire, item)
        elseif RequestBurnItem:IsA("RemoteFunction") then
            local ok, response = callUtilityRemote(RequestBurnItem, 1, fire, item)
            return ok and response ~= false
        end
        return false
    end

    send()
    local deadline = os.clock() + 0.45
    repeat
        if fireStateChanged(item, fire, beforeFuel, beforeTarget, beforeLevel) then return true end
        task.wait(0.05)
    until not state.active or os.clock() >= deadline

    if not item.Parent then return true end

    -- If the server requires proximity, stage ABOVE the touch zone so the
    -- game's local CheckInnerTouch cannot delete the item before confirmation.
    local zone = fire:FindFirstChild("InnerTouchZone", true)
    local stageCF
    if zone and zone:IsA("BasePart") then
        stageCF = zone.CFrame * CFrame.new(0, zone.Size.Y * 0.5 + 6, 0)
    else
        stageCF = fire:GetPivot() * CFrame.new(0, 10, 0)
    end
    fastResourceDrop(item, stageCF)
    if not item.Parent then return true end
    send()

    deadline = os.clock() + 0.75
    repeat
        if fireStateChanged(item, fire, beforeFuel, beforeTarget, beforeLevel) then return true end
        task.wait(0.05)
    until not state.active or os.clock() >= deadline
    return false
end

local function routeItemToScrapper(item)
    if not item or not item.Parent then return false end
    local bench = getCraftingBenchReceiver()
    if not bench then return false end
    if not isLive(RequestScrapItem) then refreshRemotes() end
    if not isLive(RequestScrapItem) then return false end

    local beforeWood, beforeScrap = getCampTotals()
    local function accepted(response)
        if response == true or (type(response) == "table" and response.Success == true) then return true end
        if not item.Parent then return true end
        local wood, scrap = getCampTotals()
        return (beforeWood ~= nil and wood ~= nil and wood > beforeWood)
            or (beforeScrap ~= nil and scrap ~= nil and scrap > beforeScrap)
    end

    local ok, response = callUtilityRemote(RequestScrapItem, 1.5, bench, item)
    if ok and accepted(response) then return true end
    if not item.Parent then return true end

    local zone = bench:FindFirstChild("TouchZone", true)
    if zone and zone:IsA("BasePart") then
        fastResourceDrop(item, zone.CFrame * CFrame.new(0, zone.Size.Y * 0.5 + 5, 0))
    end
    if not item.Parent then return true end

    ok, response = callUtilityRemote(RequestScrapItem, 1.5, bench, item)
    return ok and accepted(response)
end

local function runResourceService()'''
regex_once(
    r'local function burnItemIntoCampfire\(item\)\n.*?\nlocal function runResourceService\(\)',
    resource_block,
    'direct resource remotes',
)

# Useful runtime state in compact status, without adding another debug UI.
once(
    '"Fire %s/6 | Axe %s | Trees %d | Hit T%d/E%d\\nSmart %s | SH %s | Diamonds %s",',
    '"Fire %s/6 | Axe %s | Trees %d | Hit T%d/E%d\\nSmart %s | SH %s | Diamonds %s",',
    'status format exists',
)

TARGET.write_text(s, encoding='utf-8')
print('patched bytes', len(s.encode('utf-8')))
