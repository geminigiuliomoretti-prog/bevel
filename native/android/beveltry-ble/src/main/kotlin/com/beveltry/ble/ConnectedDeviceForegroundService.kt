package com.beveltry.ble

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder

class ConnectedDeviceForegroundService : Service() {
    override fun onCreate() {
        super.onCreate()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            getSystemService(NotificationManager::class.java).createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "Connessione WHOOP", NotificationManager.IMPORTANCE_LOW),
            )
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf(startId)
            return START_NOT_STICKY
        }
        val notification = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION") Notification.Builder(this)
        }.setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentTitle("WHOOP connesso")
            .setContentText("Sincronizzazione Bluetooth attiva")
            .setOngoing(true)
            .build()
        startForeground(NOTIFICATION_ID, notification)
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    companion object {
        private const val CHANNEL_ID = "whoop_connected_device"
        private const val NOTIFICATION_ID = 4107
        private const val ACTION_STOP = "com.beveltry.ble.STOP_CONNECTED_DEVICE"

        fun start(context: Context) {
            context.startForegroundService(Intent(context, ConnectedDeviceForegroundService::class.java))
        }

        fun stop(context: Context) {
            context.startService(Intent(context, ConnectedDeviceForegroundService::class.java).setAction(ACTION_STOP))
        }
    }
}
