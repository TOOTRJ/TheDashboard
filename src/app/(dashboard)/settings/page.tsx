"use client";

import * as React from "react";
import { Wallet, Key, Bell, Shield, Zap, ExternalLink } from "lucide-react";
import { toast } from "sonner";

import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";

const connectedWallets = [
  { address: "0x7a3d...8f2e", name: "Main Trading", balance: "$125,420", primary: true },
  { address: "0x4b9c...1a3d", name: "Cold Storage", balance: "$45,200", primary: false },
];

export default function SettingsPage() {
  const [displayName, setDisplayName] = React.useState("NeonTrader");
  const [email, setEmail] = React.useState("trader@nexus.io");
  const [errors, setErrors] = React.useState<{ displayName?: string; email?: string }>({});
  const [priceAlerts, setPriceAlerts] = React.useState(true);
  const [tradeNotifications, setTradeNotifications] = React.useState(true);
  const [weeklyReport, setWeeklyReport] = React.useState(false);
  const [defaultSlippage, setDefaultSlippage] = React.useState("0.5");
  const [tier, setTier] = React.useState("Pro");

  const handleSaveProfile = (event: React.FormEvent) => {
    event.preventDefault();
    const nextErrors: typeof errors = {};
    if (!displayName.trim()) {
      nextErrors.displayName = "Display name is required.";
    }
    if (!email.trim() || !email.includes("@")) {
      nextErrors.email = "Enter a valid email.";
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length === 0) {
      toast.success("Profile updated!", {
        description: "Your changes have been saved.",
      });
    }
  };

  const handleSavePreferences = () => {
    toast.success("Preferences saved.", {
      description: "Notification settings updated.",
    });
  };

  const handleUpgrade = () => {
    toast.success("Upgrade initiated!", {
      description: "You'll be redirected to complete payment.",
    });
  };

  const handleDisconnectWallet = (address: string) => {
    toast.success("Wallet disconnected", {
      description: `${address} has been removed from your account.`,
    });
  };

  return (
    <div className="space-y-6">
      {/* Profile Card */}
      <Card className="border-[#00fff5]/20 bg-card/80 backdrop-blur-sm">
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#00fff5]/10">
              <Shield className="h-5 w-5 text-[#00fff5]" />
            </div>
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wider text-[#00fff5]">Profile</h2>
              <p className="text-xs text-muted-foreground">Manage your account information</p>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSaveProfile} className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="displayName" className="text-xs uppercase tracking-wider text-muted-foreground">
                Display Name
              </Label>
              <Input 
                id="displayName" 
                value={displayName} 
                onChange={(event) => setDisplayName(event.target.value)}
                className="border-[#00fff5]/20 bg-[#00fff5]/5 focus:border-[#00fff5]/40"
              />
              {errors.displayName && <p className="text-xs text-[#ff3366]">{errors.displayName}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="email" className="text-xs uppercase tracking-wider text-muted-foreground">
                Email
              </Label>
              <Input 
                id="email" 
                value={email} 
                onChange={(event) => setEmail(event.target.value)}
                className="border-[#00fff5]/20 bg-[#00fff5]/5 focus:border-[#00fff5]/40"
              />
              {errors.email && <p className="text-xs text-[#ff3366]">{errors.email}</p>}
            </div>
            <div className="sm:col-span-2 flex justify-end">
              <Button 
                type="submit"
                className="bg-gradient-to-r from-[#00fff5] to-[#ff00ff] text-black hover:opacity-90"
              >
                Save Profile
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {/* Connected Wallets */}
      <Card className="border-[#ff00ff]/20 bg-card/80 backdrop-blur-sm">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#ff00ff]/10">
                <Wallet className="h-5 w-5 text-[#ff00ff]" />
              </div>
              <div>
                <h2 className="text-sm font-semibold uppercase tracking-wider text-[#ff00ff]">
                  Connected Wallets
                </h2>
                <p className="text-xs text-muted-foreground">Manage your wallet connections</p>
              </div>
            </div>
            <Button 
              variant="outline"
              className="border-[#ff00ff]/20 hover:bg-[#ff00ff]/10 hover:text-[#ff00ff]"
            >
              Connect New
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {connectedWallets.map((wallet) => (
            <div 
              key={wallet.address}
              className="flex items-center justify-between rounded-lg border border-[#ff00ff]/10 bg-[#ff00ff]/5 p-4"
            >
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#ff00ff]/10">
                  <Wallet className="h-5 w-5 text-[#ff00ff]" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-medium">{wallet.name}</p>
                    {wallet.primary && (
                      <Badge variant="outline" className="border-[#39ff14]/30 bg-[#39ff14]/10 text-[#39ff14] text-[10px]">
                        Primary
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
                  className="text-[#ff3366] hover:bg-[#ff3366]/10 hover:text-[#ff3366]"
                  onClick={() => handleDisconnectWallet(wallet.address)}
                >
                  Disconnect
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
              <p className="text-xs text-muted-foreground">Customize your terminal experience</p>
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
              checked={priceAlerts} 
              onCheckedChange={setPriceAlerts}
              className="data-[state=checked]:bg-[#39ff14]"
            />
          </div>
          <div className="flex items-center justify-between rounded-lg border border-[#bf00ff]/10 px-4 py-3">
            <div>
              <p className="text-sm font-medium">Trade Notifications</p>
              <p className="text-xs text-muted-foreground">Alerts for order fills</p>
            </div>
            <Switch 
              checked={tradeNotifications} 
              onCheckedChange={setTradeNotifications}
              className="data-[state=checked]:bg-[#39ff14]"
            />
          </div>
          <div className="flex items-center justify-between rounded-lg border border-[#bf00ff]/10 px-4 py-3">
            <div>
              <p className="text-sm font-medium">Weekly Report</p>
              <p className="text-xs text-muted-foreground">Performance summary email</p>
            </div>
            <Switch 
              checked={weeklyReport} 
              onCheckedChange={setWeeklyReport}
              className="data-[state=checked]:bg-[#39ff14]"
            />
          </div>
          <div className="sm:col-span-2 flex items-center justify-end">
            <Button 
              variant="outline" 
              onClick={handleSavePreferences}
              className="border-[#bf00ff]/20 hover:bg-[#bf00ff]/10 hover:text-[#bf00ff]"
            >
              Save Preferences
            </Button>
          </div>
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
              <p className="text-xs text-muted-foreground">Configure default trading parameters</p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">
              Default Slippage
            </Label>
            <Select value={defaultSlippage} onValueChange={setDefaultSlippage}>
              <SelectTrigger className="border-[#39ff14]/20 bg-[#39ff14]/5">
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
            <Label className="text-xs uppercase tracking-wider text-muted-foreground">
              Gas Priority
            </Label>
            <Select defaultValue="standard">
              <SelectTrigger className="border-[#39ff14]/20 bg-[#39ff14]/5">
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
              <p className="text-xs text-muted-foreground">Manage your plan and billing</p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <div className="rounded-lg border border-[#ffff00]/20 bg-[#ffff00]/5 px-4 py-3">
              <p className="text-2xl font-bold text-[#ffff00]">{tier}</p>
              <p className="text-xs text-muted-foreground">Current Plan</p>
            </div>
            <div>
              <p className="text-sm font-medium">$49/month</p>
              <p className="text-xs text-muted-foreground">Next billing: Feb 1, 2026</p>
            </div>
          </div>
          <Dialog>
            <DialogTrigger asChild>
              <Button className="bg-gradient-to-r from-[#ffff00] to-[#ff00ff] text-black hover:opacity-90">
                <Zap className="mr-2 h-4 w-4" />
                Upgrade Plan
              </Button>
            </DialogTrigger>
            <DialogContent className="border-[#ffff00]/20 bg-card">
              <DialogHeader>
                <DialogTitle className="text-[#ffff00] uppercase tracking-wider">
                  Upgrade Your Plan
                </DialogTitle>
              </DialogHeader>
              <div className="space-y-4 mt-4">
                <div className="space-y-2">
                  <Label className="text-xs uppercase tracking-wider text-muted-foreground">
                    Select Plan
                  </Label>
                  <Select value={tier} onValueChange={setTier}>
                    <SelectTrigger className="border-[#ffff00]/20 bg-[#ffff00]/5">
                      <SelectValue placeholder="Select plan" />
                    </SelectTrigger>
                    <SelectContent className="border-[#ffff00]/20 bg-card">
                      <SelectItem value="Pro">Pro - $49/mo</SelectItem>
                      <SelectItem value="Elite">Elite - $99/mo</SelectItem>
                      <SelectItem value="Whale">Whale - $249/mo</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                
                <div className="rounded-lg border border-[#ffff00]/20 bg-[#ffff00]/5 p-4 space-y-2">
                  <p className="text-sm font-medium text-[#ffff00]">Elite Features:</p>
                  <ul className="text-xs text-muted-foreground space-y-1">
                    <li className="flex items-center gap-2">
                      <div className="h-1.5 w-1.5 rounded-full bg-[#39ff14]" />
                      Advanced analytics & AI insights
                    </li>
                    <li className="flex items-center gap-2">
                      <div className="h-1.5 w-1.5 rounded-full bg-[#39ff14]" />
                      Unlimited API calls
                    </li>
                    <li className="flex items-center gap-2">
                      <div className="h-1.5 w-1.5 rounded-full bg-[#39ff14]" />
                      Priority support
                    </li>
                    <li className="flex items-center gap-2">
                      <div className="h-1.5 w-1.5 rounded-full bg-[#39ff14]" />
                      Custom alerts & notifications
                    </li>
                  </ul>
                </div>
                
                <Button 
                  onClick={handleUpgrade} 
                  className="w-full bg-gradient-to-r from-[#ffff00] to-[#ff00ff] text-black hover:opacity-90"
                >
                  <ExternalLink className="mr-2 h-4 w-4" />
                  Confirm Upgrade
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </CardContent>
      </Card>
    </div>
  );
}
