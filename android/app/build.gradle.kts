plugins {
    alias(libs.plugins.android.application)
}

// Release signing is optional: provide a keystore through Gradle properties or
// environment variables, otherwise release builds fall back to the debug key so
// they can still be side-loaded.
fun signingValue(name: String): String? =
    providers.gradleProperty("pleatview.$name").orNull
        ?: System.getenv("PLEATVIEW_" + name.uppercase())

android {
    namespace = "com.hustlesman.pleatview"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.hustlesman.pleatview"
        minSdk = 24
        targetSdk = 36
        versionCode = 2
        versionName = "0.1.1"
    }

    signingConfigs {
        val keystore = signingValue("keystore")
        if (keystore != null) {
            create("release") {
                storeFile = file(keystore)
                storePassword = signingValue("keystore_password")
                keyAlias = signingValue("key_alias")
                keyPassword = signingValue("key_password")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            signingConfig = signingConfigs.findByName("release") ?: signingConfigs.getByName("debug")
        }
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

dependencies {
    implementation(libs.androidx.core)
    implementation(libs.androidx.webkit)
    implementation(libs.media3.exoplayer)
    implementation(libs.media3.exoplayer.hls)
    implementation(libs.media3.exoplayer.dash)
    implementation(libs.media3.exoplayer.rtsp)
    implementation(libs.media3.ui)

    testImplementation(libs.junit)
    testImplementation(libs.json)
}
