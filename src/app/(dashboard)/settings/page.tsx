"use client";

import * as React from "react";
import { Wallet, Key, Bell, Shield, Zap } from "lucide-react";

import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";

const sampleWallets = [
  { address: "0x7a3d...8f2e", name: "Main Trading", balance: "$125,420", primary: true },
  { address: "0x4b9c...1a3d", name: "Cold Storage", balance: "$45,200", primary: false },
];
const exampleCurrentPlan = "Pro";

export default function SettingsPage() {
  const [selectedExamplePlan, setSelectedExamplePlan] = React.useState(exampleCurrentPlan);

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-[#00fff5]/20 bg-[#00fff5]/5 p-4">
        <Badge variant="outline">Settings preview</Badge>
        <p className="mt-2 text-sm text-muted-foreground">
          Profile, wallet, notification, trading and plan values below are examples, not your account settings.
          Theme changes are available on this device.
        </p>
      </div>
      {/* Profile Card */}
      <Card className="border-[#00fff5]/20 bg-card/80 backdrop-blur-sm">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#00fff5]/10">
              <Shield className="h-5 w-5 text-[#00fff5]" />
            </div>
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-[#00fff5]">Example Profile</h2>
              <p className="text-xs text-muted-foreground">Sample values only; account profile editing is not available yet.</p>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="displayName" className="text-xs uppercase tracking-wider text-muted-foreground">
                Display Name
              </Label>
              <Input 
                id="displayName" 
                value="Example Trader"
                readOnly
                aria-describedby="profile-unavailable"
                className="border-[#00fff5]/20 bg-[#00fff5]/5 focus:border-[#00fff5]/40"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email" className="text-xs uppercase tracking-wider text-muted-foreground">
                Email
              </Label>
              <Input 
                id="email" 
                value="trader@example.com"
                readOnly
                aria-describedby="profile-unavailable"
                className="border-[#00fff5]/20 bg-[#00fff5]/5 focus:border-[#00fff5]/40"
              />
            </div>
            <div className="sm:col-span-2 flex justify-end">
              <Button 
                type="button"
                disabled
                aria-describedby="profile-unavailable"
                className="bg-gradient-to-r from-[#00fff5] to-[#ff00ff] text-black hover:opacity-90"
              >
                Save Profile unavailable
              </Button>
            </div>
            <p id="profile-unavailable" className="sm:col-span-2 text-xs text-muted-foreground">
              Profile changes are not available yet. These sample fields cannot be saved.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Connected Wallets */}
      <Card className="border-[#ff00ff]/20 bg-card/80 backdrop-blur-sm">
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#ff00ff]/10">
                <Wallet className="h-5 w-5 text-[#ff00ff]" />
              </div>
              <div>
                <h2 className="text-sm font-semibold uppercase tracking-wider text-[#ff00ff]">
                  Example Wallets
                </h2>
                <p className="text-xs text-muted-foreground">Sample addresses and balances; no connected wallet has been loaded.</p>
              </div>
            </div>
            <Button 
              type="button"
              disabled
              aria-describedby="wallets-unavailable"
              variant="outline"
              className="border-[#ff00ff]/20 hover:bg-[#ff00ff]/10 hover:text-[#ff00ff]"
            >
              Connect unavailable
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <p id="wallets-unavailable" className="text-xs text-muted-foreground">
            Wallet connection and disconnection are not available here yet.
          </p>
          {sampleWallets.map((wallet) => (
            <div 
              key={wallet.address}
              className="flex flex-col gap-3 rounded-lg border border-[#ff00ff]/10 bg-[#ff00ff]/5 p-4 sm:flex-row sm:items-center sm:justify-between"
            >
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#ff00ff]/10">
                  <Wallet className="h-5 w-5 text-[#ff00ff]" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium">{wallet.name}</p>
                    {wallet.primary && (
                      <Badge variant="outline" className="border-[#39ff14]/30 bg-[#39ff14]/10 text-[#39ff14] text-[10px]">
                        Sample primary
                      </Badge>
                    )}
                  </div>
                  <p className="font-mono text-xs text-muted-foreground">{wallet.address}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <p className="font-mono text-sm text-[#00fff5]">{wallet.balance}</p>
                <Button 
                  variant="ghost" 
                  size="sm"
                  type="button"
                  disabled
                  aria-describedby="wallets-unavailable"
                  className="text-[#ff3366] hover:bg-[#ff3366]/10 hover:text-[#ff3366]"
                >
                  Disconnect unavailable
                </Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Preferences */}
      <Card className="border-[#bf00ff]/20 bg-card/80 backdrop-blur-sm">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#bf00ff]/10">
              <Bell className="h-5 w-5 text-[#bf00ff]" />
            </div>
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-[#bf00ff]">Preferences</h2>
              <p className="text-xs text-muted-foreground">Theme works on this device. Notification values are sample settings.</p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="flex items-center justify-between rounded-lg border border-[#bf00ff]/10 px-4 py-3">
            <div>
              <p className="text-sm font-medium">Theme</p>
              <p className="text-xs text-muted-foreground">Light or dark mode</p>
            </div>
            <ThemeToggle />
          </div>
          <div className="flex items-center justify-between rounded-lg border border-[#bf00ff]/10 px-4 py-3">
            <div>
              <p className="text-sm font-medium">Price Alerts</p>
              <p className="text-xs text-muted-foreground">Get notified on major moves</p>
            </div>
            <Switch 
              checked
              disabled
              aria-label="Sample price alerts"
              aria-describedby="preferences-unavailable"
              className="data-[state=checked]:bg-[#39ff14]"
            />
          </div>
          <div className="flex items-center justify-between rounded-lg border border-[#bf00ff]/10 px-4 py-3">
            <div>
              <p className="text-sm font-medium">Trade Notifications</p>
              <p className="text-xs text-muted-foreground">Alerts for order fills</p>
            </div>
            <Switch 
              checked
              disabled
              aria-label="Sample trade notifications"
              aria-describedby="preferences-unavailable"
              className="data-[state=checked]:bg-[#39ff14]"
            />
          </div>
          <div className="flex items-center justify-between rounded-lg border border-[#bf00ff]/10 px-4 py-3">
            <div>
              <p className="text-sm font-medium">Weekly Report</p>
              <p className="text-xs text-muted-foreground">Performance summary email</p>
            </div>
            <Switch 
              checked={false}
              disabled
              aria-label="Sample weekly report"
              aria-describedby="preferences-unavailable"
              className="data-[state=checked]:bg-[#39ff14]"
            />
          </div>
          <div className="sm:col-span-2 flex items-center justify-end">
            <Button 
              variant="outline" 
              type="button"
              disabled
              aria-describedby="preferences-unavailable"
              className="border-[#bf00ff]/20 hover:bg-[#bf00ff]/10 hover:text-[#bf00ff]"
            >
              Save Preferences unavailable
            </Button>
          </div>
          <p id="preferences-unavailable" className="sm:col-span-2 text-xs text-muted-foreground">
            Notification and email preferences cannot be saved yet.
          </p>
        </CardContent>
      </Card>

      {/* Trading Settings */}
      <Card className="border-[#39ff14]/20 bg-card/80 backdrop-blur-sm">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#39ff14]/10">
              <Key className="h-5 w-5 text-[#39ff14]" />
            </div>
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-[#39ff14]">
                Trading Settings
              </h2>
              <p className="text-xs text-muted-foreground">Example controls only; these values do not configure the bot.</p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="example-slippage" className="text-xs uppercase tracking-wider text-muted-foreground">
              Default Slippage
            </Label>
            <Select value="0.5" disabled>
              <SelectTrigger id="example-slippage" aria-describedby="trading-unavailable" className="border-[#39ff14]/20 bg-[#39ff14]/5">
                <SelectValue placeholder="Select slippage" />
              </SelectTrigger>
              <SelectContent className="border-[#39ff14]/20 bg-card">
                <SelectItem value="0.1">0.1%</SelectItem>
                <SelectItem value="0.5">0.5%</SelectItem>
                <SelectItem value="1.0">1.0%</SelectItem>
                <SelectItem value="2.0">2.0%</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="example-priority" className="text-xs uppercase tracking-wider text-muted-foreground">
              Gas Priority
            </Label>
            <Select value="standard" disabled>
              <SelectTrigger id="example-priority" aria-describedby="trading-unavailable" className="border-[#39ff14]/20 bg-[#39ff14]/5">
                <SelectValue placeholder="Select priority" />
              </SelectTrigger>
              <SelectContent className="border-[#39ff14]/20 bg-card">
                <SelectItem value="slow">Slow (Low fees)</SelectItem>
                <SelectItem value="standard">Standard</SelectItem>
                <SelectItem value="fast">Fast</SelectItem>
                <SelectItem value="instant">Instant (High fees)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <p id="trading-unavailable" className="sm:col-span-2 text-xs text-muted-foreground">
            Trading defaults cannot be changed on this page yet.
          </p>
        </CardContent>
      </Card>

      {/* Subscription */}
      <Card className="border-[#ffff00]/20 bg-card/80 backdrop-blur-sm overflow-hidden">
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-[#ffff00] via-[#ff00ff] to-[#00fff5]" />
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#ffff00]/10">
              <Zap className="h-5 w-5 text-[#ffff00]" />
            </div>
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-[#ffff00]">Subscription</h2>
              <p className="text-xs text-muted-foreground">Example plan details; your subscription and billing status are unavailable.</p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <div className="rounded-lg border border-[#ffff00]/20 bg-[#ffff00]/5 px-4 py-3">
              <p id="example-current-plan" className="text-2xl font-bold text-[#ffff00]">{exampleCurrentPlan}</p>
              <p className="text-xs text-muted-foreground">Example current plan</p>
            </div>
            <div>
              <p className="text-sm font-medium">Example price: $49/month</p>
              <p className="text-xs text-muted-foreground">No account billing information has been loaded.</p>
            </div>
          </div>
          <Dialog>
            <DialogTrigger asChild>
              <Button type="button" className="bg-gradient-to-r from-[#ffff00] to-[#ff00ff] text-black hover:opacity-90">
                <Zap className="mr-2 h-4 w-4" />
                View example plans
              </Button>
            </DialogTrigger>
            <DialogContent className="border-[#ffff00]/20 bg-card">
              <DialogHeader>
                <DialogTitle className="text-[#ffff00] uppercase tracking-wider">
                  Example Plans
                </DialogTitle>
              </DialogHeader>
              <DialogDescription>
                Sample names and prices only. Choosing a preview does not change your subscription or begin payment.
              </DialogDescription>
              <div className="space-y-4 mt-4">
                <div className="space-y-2">
                  <Label htmlFor="example-plan-choice" className="text-xs uppercase tracking-wider text-muted-foreground">
                    Preview an example plan
                  </Label>
                  <Select value={selectedExamplePlan} onValueChange={setSelectedExamplePlan}>
                    <SelectTrigger id="example-plan-choice" className="border-[#ffff00]/20 bg-[#ffff00]/5">
                      <SelectValue placeholder="Select plan" />
                    </SelectTrigger>
                    <SelectContent className="border-[#ffff00]/20 bg-card">
                      <SelectItem value="Pro">Example Pro - $49/mo</SelectItem>
                      <SelectItem value="Elite">Example Elite - $99/mo</SelectItem>
                      <SelectItem value="Whale">Example Whale - $249/mo</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                
                <div className="rounded-lg border border-[#ffff00]/20 bg-[#ffff00]/5 p-4 space-y-2">
                  <p className="text-sm font-medium text-[#ffff00]">Selected preview: {selectedExamplePlan}</p>
                  <p className="text-xs text-muted-foreground">
                    This example does not confirm plan availability, pricing or included features.
                  </p>
                </div>
                
                <Button 
                  type="button"
                  disabled
                  aria-describedby="upgrade-unavailable"
                  className="w-full bg-gradient-to-r from-[#ffff00] to-[#ff00ff] text-black hover:opacity-90"
                >
                  Upgrade unavailable
                </Button>
                <p id="upgrade-unavailable" className="text-xs text-muted-foreground">
                  Subscription upgrades and payments are not available yet.
                </p>
              </div>
            </DialogContent>
          </Dialog>
        </CardContent>
      </Card>
    </div>
  );
}
