"use client";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { STATE_COLORS } from "@/lib/probes/constants";
import type { Probe } from "@/lib/probes/types";

interface Props {
  probes: Probe[];
  onSelectProbe: (probe: Probe) => void;
}

interface TreeNode {
  probe: Probe;
  children: TreeNode[];
}

function buildTree(probes: Probe[]): TreeNode[] {
  const map = new Map<string, TreeNode>();
  for (const p of probes) {
    map.set(p.id, { probe: p, children: [] });
  }
  const roots: TreeNode[] = [];
  for (const node of map.values()) {
    if (node.probe.parent_id && map.has(node.probe.parent_id)) {
      map.get(node.probe.parent_id)!.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
}

function TreeNodeView({
  node,
  depth,
  onSelect,
}: {
  node: TreeNode;
  depth: number;
  onSelect: (p: Probe) => void;
}) {
  const p = node.probe;
  const color = STATE_COLORS[p.state];

  return (
    <div style={{ paddingLeft: depth > 0 ? 24 : 0 }}>
      <div className="flex items-center gap-2 py-1 group">
        {depth > 0 && (
          <div className="flex items-center">
            <div className="w-4 h-px bg-[#00fff5]/20" />
            <div className="w-1.5 h-1.5 rounded-full bg-[#00fff5]/40" />
          </div>
        )}
        <button
          onClick={() => onSelect(p)}
          className="flex items-center gap-2 rounded-md px-2 py-1 text-xs hover:bg-[#00fff5]/10 transition-colors"
        >
          <div
            className="h-2 w-2 rounded-full"
            style={{ backgroundColor: color }}
          />
          <span className="font-medium truncate max-w-[120px]">
            {p.probe_name}
          </span>
          <Badge
            variant="outline"
            className="text-[9px] px-1 py-0"
            style={{
              borderColor: `${color}40`,
              color,
            }}
          >
            G{p.generation}
          </Badge>
          <span className="font-mono text-[10px] text-muted-foreground">
            F:{p.fitness_score.toFixed(2)}
          </span>
        </button>
      </div>
      {node.children.map((child) => (
        <TreeNodeView
          key={child.probe.id}
          node={child}
          depth={depth + 1}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}

export function GenealogyTree({ probes, onSelectProbe }: Props) {
  const tree = buildTree(probes);

  if (probes.length === 0) {
    return (
      <Card className="border-[#bf00ff]/20 bg-card/80 backdrop-blur-sm">
        <CardContent className="py-12 text-center">
          <p className="text-sm text-muted-foreground">
            No probes yet. Start a simulation to see the genealogy tree.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-[#bf00ff]/20 bg-card/80 backdrop-blur-sm">
      <CardHeader className="pb-2">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-[#bf00ff]">
          Probe Genealogy
        </h3>
        <p className="text-xs text-muted-foreground">
          Parent-child lineage tree. Click any probe for details.
        </p>
      </CardHeader>
      <CardContent className="max-h-[400px] overflow-y-auto">
        {tree.map((root) => (
          <TreeNodeView
            key={root.probe.id}
            node={root}
            depth={0}
            onSelect={onSelectProbe}
          />
        ))}
      </CardContent>
    </Card>
  );
}
