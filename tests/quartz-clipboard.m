// SPDX-License-Identifier: Apache-2.0
#import <AppKit/AppKit.h>
#import <objc/runtime.h>
#include <spice-client.h>
#include <spice-client-gtk.h>
#include <spice/vd_agent.h>

static NSPasteboard *test_board;
static IMP original_pasteboard;

static NSPasteboard *isolated_pasteboard(id receiver, SEL selector, NSString *name)
{
    if ([name isEqualToString:NSPasteboardNameGeneral])
        return test_board;

    return ((NSPasteboard *(*)(id, SEL, NSString *))original_pasteboard)(receiver, selector, name);
}

int main(int argc, char **argv)
{
    @autoreleasepool {
        g_test_init(&argc, &argv, NULL);
        test_board = [NSPasteboard pasteboardWithUniqueName];
        Method method = class_getClassMethod([NSPasteboard class], @selector(pasteboardWithName:));
        original_pasteboard = method_setImplementation(method, (IMP)isolated_pasteboard);
        gtk_init(&argc, &argv);

        SpiceSession *session = spice_session_new();
        SpiceGtkSession *gtk_session = spice_gtk_session_get(session);
        g_object_set(gtk_session, "auto-clipboard", TRUE, NULL);
        SpiceChannel *main_channel = spice_channel_new(session, SPICE_CHANNEL_MAIN, 0);
        guint selection = VD_AGENT_CLIPBOARD_SELECTION_CLIPBOARD;
        guint type = VD_AGENT_CLIPBOARD_UTF8_TEXT;
        const char guest_text[] = "Текст из гостевой системы";
        gboolean accepted = FALSE;

        // The test injects the reply directly, without a live SPICE agent.
        g_test_expect_message("GSpice", G_LOG_LEVEL_CRITICAL, "*agent_clipboard_request*agent_connected*");
        g_signal_emit_by_name(main_channel, "main-clipboard-selection-grab",
                              selection, &type, 1u, &accepted);
        g_test_assert_expected_messages();
        g_assert_true(accepted);
        g_signal_emit_by_name(main_channel, "main-clipboard-selection",
                              selection, type, guest_text, (guint)strlen(guest_text));

        // This native read must complete without waiting for a second agent response.
        NSString *received = [test_board stringForType:NSPasteboardTypeString];
        g_assert_true([received isEqualToString:[NSString stringWithUTF8String:guest_text]]);

        [test_board clearContents];
        [test_board setString:@"Local copy" forType:NSPasteboardTypeString];
        GdkEventOwnerChange owner_change = {0};
        owner_change.reason = GDK_OWNER_CHANGE_NEW_OWNER;
        g_signal_emit_by_name(gtk_clipboard_get(GDK_SELECTION_CLIPBOARD), "owner-change", &owner_change);
        g_signal_emit_by_name(main_channel, "main-clipboard-selection",
                              selection, type, guest_text, (guint)strlen(guest_text));
        g_assert_true([[test_board stringForType:NSPasteboardTypeString] isEqualToString:@"Local copy"]);

        method_setImplementation(method, original_pasteboard);
        [test_board releaseGlobally];
        g_print("PASS: native Quartz pasteboard reads guest UTF-8 and retains a later local copy\n");
    }
    return 0;
}
