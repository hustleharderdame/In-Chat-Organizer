plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.hustlesystem.organizer"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.hustlesystem.organizer"
        minSdk = 26          // adaptive launcher icons, modern WebView
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"

        // Where the Termux-hosted Flask app listens. Change here, not in code.
        buildConfigField("String", "ORGANIZER_URL", "\"http://127.0.0.1:8410/\"")
    }

    buildFeatures {
        buildConfig = true
    }

    buildTypes {
        release {
            isMinifyEnabled = false   // one Activity and a WebView; nothing to shrink
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.activity:activity-ktx:1.9.0")
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")
}
