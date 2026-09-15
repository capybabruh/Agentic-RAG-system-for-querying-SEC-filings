import { LogOut, Plus, Trash2 } from "lucide-react"
import { useState } from "react"
import { Link, useNavigate, useParams } from "react-router-dom"

import { useAuth } from "@/auth/AuthProvider"
import { useThreads } from "@/chat/ThreadsProvider"
import {
  AlertDialog,
  AlertDialogClose,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import {
  Avatar,
  AvatarFallback,
} from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
  SidebarRail,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import type { ChatThread } from "@/lib/api"
import type { ApiError } from "@/lib/http"

export function ThreadSidebar() {
  const navigate = useNavigate()
  const { threadId } = useParams<{ threadId: string }>()
  const { session, signOut } = useAuth()
  const { threads, loading, error: listError, createThread, deleteThread } = useThreads()
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<ChatThread | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const error = listError ?? createError

  async function handleCreateThread() {
    setCreating(true)
    setCreateError(null)
    try {
      const thread = await createThread()
      navigate(`/app/thread/${thread.id}`)
    } catch (requestError) {
      setCreateError((requestError as ApiError).message)
    } finally {
      setCreating(false)
    }
  }

  async function handleConfirmDelete() {
    if (!pendingDelete) return
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteThread(pendingDelete.id)
      if (threadId === pendingDelete.id) {
        navigate("/app")
      }
      setPendingDelete(null)
    } catch (requestError) {
      setDeleteError((requestError as ApiError).message)
    } finally {
      setDeleting(false)
    }
  }

  const email = session?.user.email ?? ""
  const initial = email ? email[0]!.toUpperCase() : "?"

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="gap-3 border-b border-border px-3 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2 group-data-[collapsible=icon]:hidden">
            <img src="/logo.jpg" alt="Document Copilot logo" className="h-8 w-8 shrink-0 rounded-full object-cover" />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-foreground">Document Copilot</p>
              <p className="truncate text-xs text-muted-foreground">SEC filing assistant</p>
            </div>
          </div>
          <SidebarTrigger />
        </div>
        <Button
          onClick={handleCreateThread}
          disabled={creating}
          className="w-full justify-start gap-2 group-data-[collapsible=icon]:w-8 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:p-0"
          title="New chat"
        >
          <Plus aria-hidden="true" />
          <span className="group-data-[collapsible=icon]:hidden">New chat</span>
        </Button>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Conversations</SidebarGroupLabel>
          {loading && (
            <div className="flex flex-col gap-1 px-1">
              {Array.from({ length: 4 }).map((_, index) => (
                <SidebarMenuSkeleton key={index} />
              ))}
            </div>
          )}
          {error && (
            <p role="alert" className="px-2 py-1 text-sm text-destructive">
              {error}
            </p>
          )}
          {!loading && !error && threads.length === 0 && (
            <p className="px-2 py-1 text-sm text-muted-foreground group-data-[collapsible=icon]:hidden">
              No conversations yet.
            </p>
          )}
          <SidebarMenu>
            {threads.map((thread) => (
              <SidebarMenuItem key={thread.id}>
                <SidebarMenuButton
                  isActive={thread.id === threadId}
                  tooltip={thread.title ?? "New conversation"}
                  render={<Link to={`/app/thread/${thread.id}`} />}
                >
                  <span className="truncate">{thread.title ?? "New conversation"}</span>
                </SidebarMenuButton>
                <SidebarMenuAction
                  showOnHover
                  title="Delete conversation"
                  onClick={(event) => {
                    event.preventDefault()
                    event.stopPropagation()
                    setDeleteError(null)
                    setPendingDelete(thread)
                  }}
                >
                  <Trash2 aria-hidden="true" />
                  <span className="sr-only">Delete conversation</span>
                </SidebarMenuAction>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="border-t border-border p-2">
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button
                variant="ghost"
                className="h-auto w-full justify-start gap-2 px-2 py-2 group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:px-0"
              />
            }
          >
            <Avatar size="sm">
              <AvatarFallback>{initial}</AvatarFallback>
            </Avatar>
            <span className="min-w-0 flex-1 truncate text-left text-sm text-foreground group-data-[collapsible=icon]:hidden">
              {email}
            </span>
          </DropdownMenuTrigger>
          <DropdownMenuContent side="top" align="start" className="w-56">
            <DropdownMenuLabel className="truncate font-normal text-muted-foreground">
              {email}
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onClick={() => void signOut()}>
              <LogOut aria-hidden="true" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarFooter>
      <SidebarRail />

      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) {
            setPendingDelete(null)
            setDeleteError(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete conversation?</AlertDialogTitle>
            <AlertDialogDescription>
              {pendingDelete?.title ?? "This conversation"} will be permanently deleted. This
              action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {deleteError && (
            <p role="alert" className="mt-3 text-sm text-destructive">
              {deleteError}
            </p>
          )}
          <AlertDialogFooter>
            <AlertDialogClose disabled={deleting}>Cancel</AlertDialogClose>
            <Button variant="destructive" disabled={deleting} onClick={() => void handleConfirmDelete()}>
              {deleting ? "Deleting..." : "Delete"}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Sidebar>
  )
}
