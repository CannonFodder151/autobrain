plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.example.autobrain"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.example.autobrain"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        create("release") {
            // Keystore material comes from local.properties or -P flags / CI
            // secrets; never committed. See android/local.properties template.
            val storeFilePath = project.findProperty("storeFile") as String?
            val storePass = project.findProperty("storePassword") as String?
            val aliasName = project.findProperty("keyAlias") as String?
            val keyPass = project.findProperty("keyPassword") as String?
            if (storeFilePath != null && storePass != null &&
                aliasName != null && keyPass != null) {
                storeFile = file(storeFilePath)
                storePassword = storePass
                keyAlias = aliasName
                keyPassword = keyPass
            }
        }
    }

    buildTypes {
        release {
            // ponytail: unsigned when no keystore props are present (local
            // release builds); CI injects real secrets for production.
            signingConfig =
                if (project.hasProperty("storeFile"))
                    signingConfigs.getByName("release")
                else null
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}
