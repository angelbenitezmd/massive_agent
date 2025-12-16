"use client";

import { useState, useEffect } from "react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  GripVertical,
  Eye,
  EyeOff,
  Plus,
  Save,
  RotateCcw,
  Layout,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

export interface LayoutItem {
  id: string;
  component: string;
  visible: boolean;
  order: number;
  colSpan?: number;
}

interface LayoutEditorProps {
  items: LayoutItem[];
  onLayoutChange: (items: LayoutItem[]) => void;
  availableComponents: Array<{
    id: string;
    name: string;
    icon?: React.ReactNode;
    description?: string;
  }>;
}

function SortableItem({
  item,
  onToggleVisibility,
  onRemove,
}: {
  item: LayoutItem;
  onToggleVisibility: (id: string) => void;
  onRemove: (id: string) => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: item.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "flex items-center gap-3 p-3 rounded-lg border bg-card",
        isDragging && "shadow-lg",
        !item.visible && "opacity-50"
      )}
    >
      <button
        {...attributes}
        {...listeners}
        className="cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground"
      >
        <GripVertical className="h-5 w-5" />
      </button>

      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium">{item.component}</span>
          {!item.visible && (
            <Badge variant="outline" className="text-xs">
              Hidden
            </Badge>
          )}
          {item.colSpan && item.colSpan > 1 && (
            <Badge variant="secondary" className="text-xs">
              {item.colSpan} cols
            </Badge>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => onToggleVisibility(item.id)}
        >
          {item.visible ? (
            <Eye className="h-4 w-4" />
          ) : (
            <EyeOff className="h-4 w-4" />
          )}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-destructive hover:text-destructive"
          onClick={() => onRemove(item.id)}
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

export function LayoutEditor({
  items: initialItems,
  onLayoutChange,
  availableComponents,
}: LayoutEditorProps) {
  const [items, setItems] = useState<LayoutItem[]>(initialItems);
  const [isOpen, setIsOpen] = useState(false);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  useEffect(() => {
    setItems(initialItems);
  }, [initialItems]);

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      setItems((items) => {
        const oldIndex = items.findIndex((item) => item.id === active.id);
        const newIndex = items.findIndex((item) => item.id === over.id);

        const newItems = arrayMove(items, oldIndex, newIndex);
        // Update order numbers
        const updatedItems = newItems.map((item, index) => ({
          ...item,
          order: index,
        }));

        onLayoutChange(updatedItems);
        return updatedItems;
      });
    }
  };

  const handleToggleVisibility = (id: string) => {
    setItems((items) => {
      const updated = items.map((item) =>
        item.id === id ? { ...item, visible: !item.visible } : item
      );
      onLayoutChange(updated);
      return updated;
    });
  };

  const handleRemove = (id: string) => {
    setItems((items) => {
      const updated = items.filter((item) => item.id !== id);
      onLayoutChange(updated);
      return updated;
    });
  };

  const handleAdd = (componentId: string) => {
    const component = availableComponents.find((c) => c.id === componentId);
    if (!component) return;

    const newItem: LayoutItem = {
      id: `${componentId}-${Date.now()}`,
      component: component.name,
      visible: true,
      order: items.length,
    };

    setItems((items) => {
      const updated = [...items, newItem];
      onLayoutChange(updated);
      return updated;
    });
  };

  const handleReset = () => {
    setItems(initialItems);
    onLayoutChange(initialItems);
  };

  const handleSave = () => {
    // Save to localStorage
    localStorage.setItem("dashboard-layout", JSON.stringify(items));
    setIsOpen(false);
  };

  const visibleItems = items.filter((item) => item.visible);
  const hiddenItems = items.filter((item) => !item.visible);
  const usedComponents = new Set(items.map((item) => item.component));
  const availableToAdd = availableComponents.filter(
    (comp) => !usedComponents.has(comp.name)
  );

  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" className="h-7 w-7">
          <Layout className="h-4 w-4" />
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl max-h-[90vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Layout className="h-5 w-5" />
            Dashboard Layout Editor
          </DialogTitle>
          <DialogDescription>
            Drag and drop to rearrange components, toggle visibility, or add new
            widgets.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Available Components to Add */}
          {availableToAdd.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium">Add Components</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {availableToAdd.map((comp) => (
                  <Button
                    key={comp.id}
                    variant="outline"
                    size="sm"
                    onClick={() => handleAdd(comp.id)}
                    className="gap-2"
                  >
                    <Plus className="h-3 w-3" />
                    {comp.name}
                  </Button>
                ))}
              </div>
            </div>
          )}

          <Separator />

          {/* Visible Components */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">
                Visible Components ({visibleItems.length})
              </span>
            </div>
            <ScrollArea className="h-[300px] pr-4">
              <DndContext
                sensors={sensors}
                collisionDetection={closestCenter}
                onDragEnd={handleDragEnd}
              >
                <SortableContext
                  items={visibleItems.map((item) => item.id)}
                  strategy={verticalListSortingStrategy}
                >
                  <div className="space-y-2">
                    {visibleItems.map((item) => (
                      <SortableItem
                        key={item.id}
                        item={item}
                        onToggleVisibility={handleToggleVisibility}
                        onRemove={handleRemove}
                      />
                    ))}
                  </div>
                </SortableContext>
              </DndContext>
            </ScrollArea>
          </div>

          {/* Hidden Components */}
          {hiddenItems.length > 0 && (
            <>
              <Separator />
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-muted-foreground">
                    Hidden Components ({hiddenItems.length})
                  </span>
                </div>
                <ScrollArea className="h-[150px] pr-4">
                  <div className="space-y-2">
                    {hiddenItems.map((item) => (
                      <div
                        key={item.id}
                        className="flex items-center gap-3 p-3 rounded-lg border bg-muted/50 opacity-60"
                      >
                        <EyeOff className="h-4 w-4 text-muted-foreground" />
                        <span className="flex-1 font-medium">
                          {item.component}
                        </span>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => handleToggleVisibility(item.id)}
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </div>
            </>
          )}

          {/* Actions */}
          <div className="flex items-center justify-between pt-4 border-t">
            <Button variant="outline" onClick={handleReset} className="gap-2">
              <RotateCcw className="h-4 w-4" />
              Reset to Default
            </Button>
            <Button onClick={handleSave} className="gap-2">
              <Save className="h-4 w-4" />
              Save Layout
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
