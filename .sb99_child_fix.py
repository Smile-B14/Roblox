from pathlib import Path

p = Path('99 Nights Helper Godmode')
s = p.read_text(encoding='utf-8')

replacements = [
    (
        '''        -- Grab any already-streamed child first.\n        storeCurrentlyLoaded()\n\n        -- Then visit each MissingKids position and immediately bag whatever\n''',
        '''        -- Grab any already-streamed child first. Children already stored by a\n        -- previous retry remain in ItemBag; never unload a partial rescue set.\n        storeCurrentlyLoaded()\n\n        -- Then visit each MissingKids position and immediately bag whatever\n''',
        'child intro',
    ),
    (
        '''            if verifiedChildCount() + (function()\n                local n = 0\n                for _ in pairs(storedNames) do n = n + 1 end\n                return n\n            end)() >= 4 then\n                break\n            end\n''',
        '''            if verifiedChildCount() + #getBaggedChildren() >= 4 then\n                break\n            end\n''',
        'child count',
    ),
    (
        '''        if next(usedBags) ~= nil or #getBaggedChildren() > 0 then\n            dropChildrenAtCamp(usedBags)\n        end\n\n        task.wait(1)\n        getUnrescuedChildren()\n        success = verifiedChildCount() >= 4\n''',
        '''        local alreadyVerified = verifiedChildCount()\n        local baggedCount = #getBaggedChildren()\n        local neededInBag = math.max(0, 4 - alreadyVerified)\n\n        -- Keep partial progress in the sack between attempts. Only return to\n        -- camp once every remaining child is actually stored.\n        if neededInBag == 0 then\n            success = true\n        elseif baggedCount >= neededInBag then\n            dropChildrenAtCamp(usedBags)\n            local verifyDeadline = os.clock() + 5\n            repeat\n                task.wait(0.2)\n                getUnrescuedChildren()\n                success = verifiedChildCount() >= 4\n            until success or not state.autoFarm or os.clock() >= verifyDeadline\n        else\n            success = false\n        end\n''',
        'partial child drop',
    ),
    (
        '''    local before = getSackStoredCount(sack)\n    local ok, response = callUtilityRemote(RequestBagStoreItem, 2, sack, child)\n''',
        '''    local before = getSackStoredCount(sack)\n    equipOwnedItem(sack)\n\n    local client = getGameClient()\n    local interactionHandler = client and client.InteractionHandler\n    local interactions = interactionHandler and interactionHandler.Interactions\n    if interactions and type(interactions.CanBeBagged) == "function" then\n        pcall(interactions.CanBeBagged, child)\n        local interactionDeadline = os.clock() + 1\n        repeat\n            if childStoredInItemBag(childName) or getSackStoredCount(sack) > before then\n                state.childRescueObserved[childName] = true\n                return true\n            end\n            task.wait(0.06)\n        until not state.active or os.clock() >= interactionDeadline\n        child = reacquireChild(childName) or child\n        if not child or not child.Parent then\n            return childStoredInItemBag(childName)\n        end\n    end\n\n    local ok, response = callUtilityRemote(RequestBagStoreItem, 2, sack, child)\n''',
        'exact CanBeBagged path',
    ),
]

for old, new, label in replacements:
    count = s.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1, got {count}')
    s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8')
print('child integration patched')
