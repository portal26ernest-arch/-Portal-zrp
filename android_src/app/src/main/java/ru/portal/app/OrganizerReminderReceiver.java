package ru.portal.app;

import android.app.NotificationManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.app.PendingIntent;
import android.content.pm.PackageManager;
import android.Manifest;
import android.os.Build;
import androidx.core.app.NotificationCompat;
import androidx.core.content.ContextCompat;

public final class OrganizerReminderReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return;
        String id = intent.getStringExtra("id");
        if (id == null || id.length() > 80) return;
        NotificationManager manager = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
        if (manager == null) return;
        String title = intent.getStringExtra("title");
        Intent open = new Intent(context, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        PendingIntent content = PendingIntent.getActivity(context, id.hashCode(), open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        manager.notify(id.hashCode(), new NotificationCompat.Builder(context, "organizer_reminders")
            .setSmallIcon(R.drawable.ic_portal).setContentTitle("Напоминание PORTAL")
            .setContentText(title == null ? "Задача" : title).setContentIntent(content).setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT).build());
    }
}
