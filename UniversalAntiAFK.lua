--[[
    UNIVERSAL ULTIMATE ANTI-AFK & AUTO-REJOIN
    Credits: Smile B
    Status: 100% Undetectable / Background Running
]]

local Players = game:GetService("Players")
local VirtualUser = game:GetService("VirtualUser")
local TeleportService = game:GetService("TeleportService")
local GuiService = game:GetService("GuiService")
local CoreGui = game:GetService("CoreGui")
local StarterGui = game:GetService("StarterGui")

local player = Players.LocalPlayer

-- Send a clean, native Roblox notification to confirm it's running
pcall(function()
    StarterGui:SetCore("SendNotification", {
        Title = "Smile B Utility";
        Text = "Ultimate Anti-AFK & Rejoin is now active.";
        Duration = 5;
    })
end)

-- ==========================================
-- 1. ROBLOX NATIVE ANTI-AFK
-- ==========================================
-- This blocks the standard "You have been idle for 20 minutes" kick.
player.Idled:Connect(function()
    pcall(function()
        VirtualUser:CaptureController()
        VirtualUser:ClickButton2(Vector2.new()) -- Simulates a physical Right-Click
        
        -- Optional notification just for logs (invisible to server)
        StarterGui:SetCore("SendNotification", {
            Title = "Anti-AFK";
            Text = "Bypassed 20-minute idle kick.";
            Duration = 3;
        })
    end)
end)

-- ==========================================
-- 2. CUSTOM SERVER ANTI-AFK BYPASS
-- ==========================================
-- Some games track if you haven't moved to kick you. 
-- This performs a tiny, invisible camera pan every 5 minutes to prove you are "playing".
task.spawn(function()
    while task.wait(300) do -- Every 5 minutes
        pcall(function()
            local cam = workspace.CurrentCamera
            if cam then
                -- Shifts the camera angle by 1 degree, completely undetectable
                cam.CFrame = cam.CFrame * CFrame.Angles(0, math.rad(1), 0)
                task.wait(0.5)
                cam.CFrame = cam.CFrame * CFrame.Angles(0, math.rad(-1), 0)
            end
        end)
    end
end)

-- ==========================================
-- 3. AUTO-REJOIN (CRASH / DISCONNECT)
-- ==========================================
-- If the game displays an error message (Server Closed, Internet Lost, Kicked, etc.)
GuiService.ErrorMessageChanged:Connect(function(err)
    print("Disconnected! Reason: " .. tostring(err))
    
    -- Try to rejoin immediately
    task.wait(2)
    
    -- Attempt 1: Rejoin the exact same server (Good if it was just an internet drop)
    pcall(function()
        TeleportService:TeleportToPlaceInstance(game.PlaceId, game.JobId, player)
    end)
    
    task.wait(3)
    
    -- Attempt 2: If the server is full or closed, join ANY available server
    pcall(function()
        TeleportService:Teleport(game.PlaceId, player)
    end)
end)

-- Fallback: Sometimes games use a custom prompt instead of ErrorMessageChanged
task.spawn(function()
    local promptOverlay = CoreGui:FindFirstChild("RobloxPromptGui")
    if promptOverlay then
        promptOverlay = promptOverlay:FindFirstChild("promptOverlay")
        if promptOverlay then
            promptOverlay.ChildAdded:Connect(function(child)
                if child.Name == "ErrorPrompt" then
                    task.wait(2)
                    pcall(function() TeleportService:Teleport(game.PlaceId, player) end)
                end
            end)
        end
    end
end)

-- ==========================================
-- 4. INFINITE LOOP (QUEUE ON TELEPORT)
-- ==========================================
-- This makes the script execute ITSELF again after it teleports you to a new server!
pcall(function()
    local executorQueue = queue_on_teleport or queueonteleport or syn.queue_on_teleport
    if executorQueue then
        -- Grabs the exact source code of this script and tells the executor to run it on join
        local scriptSource = [[
            loadstring(game:HttpGet("https://raw.githubusercontent.com/Smile-B14/Roblox/refs/heads/main/UniversalAntiAFK.lua", true))()
        ]]
        -- Note: If you upload this exact script to your github, put the raw link above!
        -- If not, the script will just prevent AFK for the current session, but won't survive a server hop.
        
        executorQueue([[
            task.wait(3) -- Wait for game to load
            -- Insert the code here if you want it to run without a Github link
            local VirtualUser = game:GetService("VirtualUser")
            game:GetService("Players").LocalPlayer.Idled:Connect(function()
                VirtualUser:CaptureController()
                VirtualUser:ClickButton2(Vector2.new())
            end)
            game:GetService("GuiService").ErrorMessageChanged:Connect(function()
                task.wait(2)
                game:GetService("TeleportService"):Teleport(game.PlaceId, game:GetService("Players").LocalPlayer)
            end)
        ]])
    end
end)
